"""Planning and applying changes.

Install and removal are split into `plan_*` (pure: reads the bundle, decides
everything, touches nothing) and `apply_*` (which performs the writes). That
split is what makes `--dry-run` honest — it prints the same plan that would be
executed — and it gives the GUI a preview to show before anything changes.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import desktop, fetch, paths, squashfs
from .appimage import Bundle, inspect
from .errors import AlreadyInstalled, AppimoError, UnreadableBundle
from .state import InstalledApp, State
from .util import build_exec, png_size, slugify

MODE_KEEP = "keep"
MODE_EXTRACT = "extract"

#: Root of the launcher id namespace, e.g. `dev.appimo.gnome-boxes`.
ID_PREFIX = "dev.appimo"
ID_SUFFIX = ".desktop"


@dataclass
class IconWrite:
    path: Path
    data: bytes
    described: str


@dataclass
class InstallOptions:
    app_id: str = ""
    name: str = ""
    apps_dir: Path | None = None
    mode: str = MODE_KEEP
    copy: bool = False
    force: bool = False
    with_icon: bool = True
    unsafe_extract: bool = False
    timeout: int = 300
    #: An https:// URL to download instead of reading a local file.
    url: str = ""
    #: Replace an existing install even when its hash is unchanged (upgrade).
    refresh: bool = False


@dataclass
class InstallPlan:
    """Everything that will happen, before anything happens."""

    bundle: Bundle
    app_id: str
    name: str
    mode: str
    managed_path: Path
    desktop_path: Path
    desktop_contents: str
    exec_value: str
    icon: IconWrite | None
    moves: list[tuple[Path, Path]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    replaced: InstalledApp | None = None
    #: Unpacking supersedes the AppImage; leaving it behind would recreate the
    #: very orphan-in-Downloads problem this tool exists to fix.
    remove_source: bool = False
    #: SHA-256 of the source bundle, recorded in state for `appimo upgrade`.
    source_sha256: str = ""

    def summary(self) -> list[tuple[str, str]]:
        """Aligned (label, value) rows — the same shape for dry-run and apply."""
        rows = [
            ("reading", self.bundle.source.name),
            ("name", self.name),
            ("id", self.app_id),
        ]
        if self.icon:
            rows.append(("icon", f"found {self.icon.described}"))
        else:
            rows.append(("icon", "none found — using a generic icon"))
        if self.mode == MODE_EXTRACT:
            rows.append(("unpacked", self.managed_path))
            if self.remove_source:
                rows.append(("removed", self.bundle.source))
        else:
            verb = "copied" if not self.moves else "moved"
            rows.append((verb, self.managed_path))
        rows.append(("launcher", self.desktop_path))
        return rows


@dataclass
class RemovePlan:
    app: InstalledApp
    actions: list[tuple[str, str]]


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def _safe_filename(name: str) -> str:
    """A filename that keeps the app's human name but cannot escape the dir."""
    cleaned = name.replace("/", "-").replace("\0", "").strip().strip(".")
    cleaned = " ".join(cleaned.split())
    return cleaned[:120] or "app"


def make_app_id(name: str, override: str = "") -> str:
    """The launcher id: namespaced so we never shadow a distro's own entry."""
    if override:
        raw = override.strip()
        if raw.endswith(ID_SUFFIX):
            raw = raw[: -len(ID_SUFFIX)]
        return raw
    return f"{ID_PREFIX}.{slugify(name)}"


def icon_destination(app_id: str, kind: str, size: int | None) -> Path:
    """Where an icon belongs in the user's hicolor theme."""
    if kind == "svg" or not size:
        return paths.hicolor_dir() / "scalable" / "apps" / f"{app_id}.svg"
    return paths.hicolor_dir() / f"{size}x{size}" / "apps" / f"{app_id}.png"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def plan_install(
    source: Path,
    options: InstallOptions | None = None,
    state: State | None = None,
) -> InstallPlan:
    """Work out the whole installation without writing anything."""
    options = options or InstallOptions()
    state = state or State.load()
    source = source.expanduser()

    if not source.exists():
        # Installing moves the file out of Downloads, so re-running the same
        # command is a common mistake. Say what happened instead of "no such
        # file", which is technically true and completely unhelpful.
        for known in state.apps.values():
            if known.source and Path(known.source) == source:
                raise AlreadyInstalled(
                    f"'{known.name}' was already integrated from this file",
                    hint=f"it now lives at {known.managed_path}; "
                    f"run 'appimo remove {known.name}' to undo",
                )

    bundle = inspect(source, unsafe_extract=options.unsafe_extract, timeout=options.timeout)
    metadata = bundle.metadata

    name = options.name or metadata.name or source.stem
    app_id = make_app_id(name, options.app_id)

    existing = state.apps.get(app_id)
    if existing and not options.force:
        raise AlreadyInstalled(
            f"'{name}' is already integrated ({existing.desktop_file})",
            hint="use --force to replace it, or 'appimo remove' first",
        )

    apps_dir = options.apps_dir or paths.default_apps_dir()
    warnings: list[str] = []

    if options.mode == MODE_EXTRACT:
        managed_path = apps_dir / _safe_filename(name)
        command = str(managed_path / "AppRun")
        if "AppRun" not in bundle.members:
            raise UnreadableBundle(
                f"{source.name} has no AppRun to launch",
                hint="drop --extract to keep the AppImage intact instead",
            )
    else:
        managed_path = apps_dir / f"{_safe_filename(name)}.AppImage"
        command = str(managed_path)

    # Preserve whatever arguments the bundle asked for (%U, %F, --flags...).
    exec_value = build_exec(command, metadata.exec_arguments)

    icon_write: IconWrite | None = None
    if options.with_icon:
        candidate = bundle.best_icon()
        data = bundle.read(candidate.member) if candidate else None
        if candidate and data:
            kind, size, described = candidate.kind, candidate.size, candidate.described
            if kind == "png" and not size:
                # Root-level icons carry no size hint; read the real dimensions
                # so the icon lands in the right hicolor bucket.
                real = png_size(data)
                if real:
                    size = max(real)
                    described = f"{size}x{size} PNG"
            icon_write = IconWrite(icon_destination(app_id, kind, size), data, described)
        elif candidate is None:
            warnings.append("no icon inside the bundle; your theme's default will be used")
        else:
            warnings.append(f"could not read {candidate.member}; skipping the icon")

    desktop_contents = desktop.render(
        app_id=app_id,
        name=name,
        exec_value=exec_value,
        icon_name=app_id if icon_write else metadata.icon_name or "application-x-executable",
        comment=metadata.comment,
        categories=metadata.categories or ["Utility"],
        mime_types=metadata.mime_types,
        terminal=metadata.terminal,
        startup_wm_class=metadata.startup_wm_class,
        source=str(bundle.source),
        managed_path=str(managed_path),
        extra=metadata.passthrough,
    )

    if metadata.terminal:
        warnings.append("this is a terminal application; it will open in a terminal")
    if not metadata.comment:
        warnings.append("the bundle carries no description")
    if os.geteuid() == 0 and not os.environ.get("APPIMO_ALLOW_ROOT"):
        from .errors import RefusedAsRoot

        raise RefusedAsRoot(
            "Appimo installs into the invoking user's home, so running it as root "
            "would create launchers owned by root",
            hint="run it as your normal user instead",
        )

    return InstallPlan(
        bundle=bundle,
        app_id=app_id,
        name=name,
        mode=options.mode if options.mode == MODE_EXTRACT else MODE_KEEP,
        managed_path=managed_path,
        desktop_path=paths.applications_dir() / f"{app_id}{ID_SUFFIX}",
        desktop_contents=desktop_contents,
        exec_value=exec_value,
        icon=icon_write,
        moves=[(bundle.source, managed_path)]
        if options.mode == MODE_KEEP and not options.copy
        else [],
        warnings=warnings,
        replaced=existing,
        remove_source=options.mode == MODE_EXTRACT and not options.copy,
        source_sha256=fetch.sha256_of(bundle.source) if bundle.source.is_file() else "",
    )


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


class _Undo:
    """Best-effort rollback so a failed install never leaves a broken launcher."""

    def __init__(self) -> None:
        self.created_files: list[Path] = []
        self.created_dirs: list[Path] = []
        self.moved: list[tuple[Path, Path]] = []

    def note_file(self, path: Path) -> None:
        self.created_files.append(path)

    def note_dir(self, path: Path) -> None:
        self.created_dirs.append(path)

    def note_move(self, original: Path, new: Path) -> None:
        self.moved.append((original, new))

    def run(self) -> None:
        for original, new in reversed(self.moved):
            try:
                if new.exists() and not original.exists():
                    shutil.move(str(new), str(original))
            except OSError:
                pass
        for path in reversed(self.created_files):
            try:
                path.unlink()
            except OSError:
                pass
        for path in reversed(self.created_dirs):
            try:
                shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass


def apply_install(plan: InstallPlan, options: InstallOptions, state: State) -> InstalledApp:
    """Perform the plan. Rolls back on failure and returns the new record."""
    undo = _Undo()
    icon_files: list[str] = []

    try:
        if plan.mode == MODE_EXTRACT:
            plan.managed_path.parent.mkdir(parents=True, exist_ok=True)
            if plan.managed_path.exists():
                shutil.rmtree(plan.managed_path)
            undo.note_dir(plan.managed_path)
            if plan.bundle.is_directory:
                # Already-exploded input: a straight copy is the unpacking.
                shutil.copytree(plan.bundle.source, plan.managed_path, symlinks=True)
            else:
                assert plan.bundle.offset is not None
                squashfs.extract_all(
                    plan.bundle.source,
                    plan.bundle.offset,
                    plan.managed_path,
                    timeout=options.timeout,
                )
            apprun = plan.managed_path / "AppRun"
            if apprun.exists():
                apprun.chmod(apprun.stat().st_mode | 0o111)
        else:
            plan.managed_path.parent.mkdir(parents=True, exist_ok=True)
            if plan.managed_path.exists() and plan.managed_path != plan.bundle.source:
                plan.managed_path.unlink()
            if options.copy:
                shutil.copy2(plan.bundle.source, plan.managed_path)
            else:
                shutil.move(str(plan.bundle.source), str(plan.managed_path))
                undo.note_move(plan.bundle.source, plan.managed_path)
            plan.managed_path.chmod(plan.managed_path.stat().st_mode | 0o111)

        if plan.icon:
            plan.icon.path.parent.mkdir(parents=True, exist_ok=True)
            plan.icon.path.write_bytes(plan.icon.data)
            undo.note_file(plan.icon.path)
            icon_files.append(str(plan.icon.path))

        plan.desktop_path.parent.mkdir(parents=True, exist_ok=True)
        plan.desktop_path.write_text(plan.desktop_contents, encoding="utf-8")
        undo.note_file(plan.desktop_path)

        messages = desktop.validate(plan.desktop_path)
        errors = [m for m in messages if ": error" in m or ":error" in m]
        if errors:
            raise AppimoError(
                "the generated launcher failed validation",
                hint=errors[0],
            )

        record = InstalledApp(
            id=plan.app_id,
            name=plan.name,
            desktop_file=str(plan.desktop_path),
            managed_path=str(plan.managed_path),
            mode=plan.mode,
            # A downloaded bundle records its URL: the temp file is deleted,
            # and `appimo upgrade` re-downloads from the source.
            source=options.url or str(plan.bundle.source),
            sha256=plan.source_sha256,
            icon_files=icon_files,
            version=plan.bundle.metadata.passthrough.get("X-AppImage-Version", ""),
            installed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        state.add(record)
        state.save()
    except BaseException:
        undo.run()
        raise

    # Deliberately the last step, and outside the rollback scope: the install is
    # already durably recorded, so a failure here only leaves a stray file.
    if plan.remove_source:
        try:
            plan.bundle.source.unlink()
        except OSError:
            pass

    desktop.refresh_databases(
        plan.desktop_path.parent, mime_types=bool(plan.bundle.metadata.mime_types)
    )
    return record


def plan_remove(key: str, *, keep_files: bool = False, state: State | None = None) -> RemovePlan:
    state = state or State.load()
    app = state.find(key)

    actions: list[tuple[str, str]] = [
        ("launcher", Path(app.desktop_file)),
    ]
    for icon in app.icon_files:
        actions.append(("icon", Path(icon)))
    if not keep_files:
        actions.append(("remove", Path(app.managed_path)))
    return RemovePlan(app=app, actions=actions)


def apply_remove(plan: RemovePlan, *, keep_files: bool = False, state: State | None = None) -> None:
    state = state or State.load()
    app = plan.app

    try:
        Path(app.desktop_file).unlink()
    except FileNotFoundError:
        pass

    for icon in app.icon_files:
        try:
            Path(icon).unlink()
        except FileNotFoundError:
            pass

    if not keep_files:
        target = Path(app.managed_path)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()

    state.remove(app.id)
    state.save()
    desktop.refresh_databases(
        Path(app.desktop_file).parent, mime_types=False
    )


__all__ = [
    "IconWrite",
    "InstallOptions",
    "InstallPlan",
    "MODE_EXTRACT",
    "MODE_KEEP",
    "RemovePlan",
    "apply_install",
    "apply_remove",
    "plan_install",
    "plan_remove",
]
