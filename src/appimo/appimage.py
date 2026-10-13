"""Inspecting a bundle: what is it called, what icon does it carry.

Turns any of AppImage / SquashFS / extracted AppDir into a `Bundle`: metadata
plus ranked icon candidates. Everything here is read-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import squashfs
from .desktop import AppMetadata, DesktopEntry
from .errors import NoDesktopEntry, NotAnAppImage, UnreadableBundle
from .util import image_kind, png_size

#: How we read the payload. `unsquashfs` never executes the bundle.
SAFE = "unsquashfs"
#: Last resort: ask the bundle's own runtime to extract itself.
UNSAFE = "appimage-extract"
APPDIR = "appdir"


@dataclass
class IconCandidate:
    """One icon found inside the bundle, with a preference score."""

    member: str
    kind: str
    size: int | None
    score: int

    @property
    def described(self) -> str:
        if self.kind == "svg":
            return "scalable SVG"
        if self.size:
            return f"{self.size}x{self.size} {self.kind.upper()}"
        return self.kind.upper()


@dataclass
class Bundle:
    """A readable AppImage, SquashFS image or extracted AppDir."""

    source: Path
    kind: str
    offset: int | None
    members: list[str]
    metadata: AppMetadata
    icons: list[IconCandidate] = field(default_factory=list)
    desktop_member: str = ""
    #: Set when the payload was materialised on disk (unsafe/extract modes).
    workdir: Path | None = None

    @property
    def is_directory(self) -> bool:
        return self.kind == APPDIR

    def read(self, member: str, *, timeout: int = 120) -> bytes | None:
        """Read one file out of the bundle."""
        if self.is_directory:
            candidate = self.source / member
            try:
                return candidate.read_bytes()
            except OSError:
                return None
        assert self.offset is not None
        if self.workdir is not None:
            candidate = self.workdir / member
            try:
                return candidate.read_bytes()
            except OSError:
                return None
        return squashfs.read_member(self.source, self.offset, member, timeout=timeout)

    def best_icon(self) -> IconCandidate | None:
        return self.icons[0] if self.icons else None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def _appdir_members(root: Path) -> list[str]:
    members = []
    for item in root.rglob("*"):
        try:
            members.append(str(item.relative_to(root)))
        except ValueError:  # pragma: no cover - defensive
            continue
    return members


def _find_desktop_member(members: list[str], stem: str) -> str | None:
    """Pick the AppDir's root desktop file, preferring one named after the app."""
    roots = [m for m in members if "/" not in m and m.endswith(".desktop")]
    if not roots:
        return None
    if len(roots) > 1:
        cleaned = [m for m in roots if not m.startswith(".")]
        roots = cleaned or roots
        for member in roots:
            if Path(member).stem.lower() == stem.lower():
                return member
    return sorted(roots)[0]


def _score_icons(members: list[str], icon_name: str, stem: str) -> list[IconCandidate]:
    """Rank every plausible icon in the bundle, best first.

    Order of preference follows the AppDir convention: the root icon named by
    the desktop file's `Icon=` key, then `.DirIcon`, then the hicolor theme
    tree, then `pixmaps`, then anything that looks like a PNG or SVG.
    """
    names = {n for n in (icon_name, stem) if n}
    candidates: list[IconCandidate] = []

    for member in members:
        path = Path(member)
        suffix = path.suffix.lower()
        if suffix not in {".png", ".svg", ".xpm"} and member != ".DirIcon":
            continue

        score = 0
        is_root = "/" not in member
        named = path.stem in names or path.name in names

        if member == ".DirIcon":
            score = 80
        elif is_root and named:
            score = 100
        elif is_root:
            score = 30
        elif "icons/hicolor" in member and "/apps/" in member:
            score = 70
        elif "icons" in member and "/apps/" in member:
            score = 60
        elif "pixmaps" in member:
            score = 50
        else:
            score = 20

        if score in {100, 80, 70, 60, 50} and not named and path.stem != ".DirIcon":
            score -= 15

        # A scalable icon beats a small raster one, but not a 512px PNG.
        if suffix == ".svg":
            score += 8
            size = None
        elif suffix == ".png":
            size = None
            if "hicolor" in member:
                for part in path.parts:
                    if "x" in part and part.split("x")[0].isdigit():
                        size = int(part.split("x")[0])
                        break
            candidates.append(IconCandidate(member, "png", size, score + (size or 0) // 16))
            continue
        else:
            size = None

        candidates.append(IconCandidate(member, suffix.lstrip("."), size, score))

    # Sort by score, then prefer larger rasters.
    return sorted(candidates, key=lambda c: (c.score, c.size or 0), reverse=True)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


def _inspect_appdir(source: Path) -> Bundle:
    members = _appdir_members(source)
    stem = source.name
    member = _find_desktop_member(members, stem)
    if not member:
        raise NoDesktopEntry(
            f"{source} has no .desktop file",
            hint="an AppDir needs one at its root to describe the application",
        )
    raw = (source / member).read_text(encoding="utf-8", errors="replace")
    entry = DesktopEntry.parse(raw)
    metadata = AppMetadata.from_entry(entry, source_id=Path(member).stem)
    if not metadata.name:
        metadata.name = stem
    return Bundle(
        source=source,
        kind=APPDIR,
        offset=None,
        members=members,
        metadata=metadata,
        icons=_score_icons(members, metadata.icon_name, stem),
        desktop_member=member,
    )


def _extract_with_runtime(source: Path, timeout: int) -> Path:
    """Fallback: let the bundle extract itself. Executes the bundle's runtime."""
    if not os.access(source, os.X_OK):
        raise UnreadableBundle(
            f"{source.name} is not executable",
            hint=f"run: chmod +x {source}",
        )
    workdir = Path(tempfile.mkdtemp(prefix="appimo-extract-"))
    result = subprocess.run(
        [str(source.resolve()), "--appimage-extract"],
        cwd=workdir,
        capture_output=True,
        timeout=timeout,
    )
    produced = workdir / "squashfs-root"
    if result.returncode != 0 or not produced.is_dir():
        shutil.rmtree(workdir, ignore_errors=True)
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise UnreadableBundle(
            f"{source.name} could not be unpacked",
            hint=detail[-1] if detail else "the file may be truncated",
        )
    return produced


def inspect(
    source: Path,
    *,
    unsafe_extract: bool = False,
    timeout: int = 300,
) -> Bundle:
    """Read a bundle's metadata and icons without executing it.

    `unsafe_extract` opts into running the bundle's own runtime, which is only
    needed on systems without `unsquashfs` or for exotic bundles our offset
    scan can't parse.
    """
    source = source.expanduser()
    if not source.exists():
        raise NotAnAppImage(f"no such file: {source}")

    if source.is_dir():
        return _inspect_appdir(source)

    offset = squashfs.scan_offset(source)

    if offset is None:
        if not unsafe_extract:
            raise NotAnAppImage(
                f"{source.name} is not an AppImage or SquashFS image",
                hint="if you are sure it is, retry with --unsafe-extract",
            )
        workdir = _extract_with_runtime(source, timeout)
        return _inspect_appdir(workdir)

    if squashfs.unsquashfs_path() is None:
        if not unsafe_extract:
            raise UnreadableBundle(
                "unsquashfs is missing, so Appimo cannot read the bundle safely",
                hint="install squashfs-tools, or pass --unsafe-extract",
            )
        workdir = _extract_with_runtime(source, timeout)
        bundle = _inspect_appdir(workdir)
        bundle.source = source
        bundle.kind = UNSAFE
        bundle.offset = offset
        return bundle

    members = squashfs.list_members(source, offset, timeout=timeout)
    stem = source.stem
    member = _find_desktop_member(members, stem)
    if not member:
        raise NoDesktopEntry(
            f"{source.name} carries no .desktop file",
            hint="this bundle cannot be integrated automatically",
        )
    raw = squashfs.read_member(source, offset, member, timeout=timeout)
    if raw is None:
        raise UnreadableBundle(f"could not read {member} from {source.name}")
    entry = DesktopEntry.parse(raw.decode("utf-8", "replace"))
    metadata = AppMetadata.from_entry(entry, source_id=Path(member).stem)
    if not metadata.name:
        metadata.name = stem

    return Bundle(
        source=source,
        kind="appimage" if _is_elf(source) else "squashfs",
        offset=offset,
        members=members,
        metadata=metadata,
        icons=_score_icons(members, metadata.icon_name, stem),
        desktop_member=member,
    )
