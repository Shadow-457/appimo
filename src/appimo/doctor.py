"""`appimo doctor` — explain the environment instead of failing obscurely.

Most AppImage problems are environmental: no `unsquashfs`, an old runtime that
wants FUSE 2, a file that lost its execute bit, or a launcher directory that
isn't writable. Doctor names the problem and the fix.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import paths, squashfs

OK = "ok"
INFO = "info"
WARN = "warn"
FAIL = "fail"


@dataclass
class Check:
    status: str
    label: str
    detail: str = ""
    hint: str = ""


def _find_libfuse2() -> str | None:
    """Locate libfuse.so.2, the ABI old AppImage runtimes dlopen."""
    candidates = [
        "/usr/lib/x86_64-linux-gnu/libfuse.so.2",
        "/usr/lib/aarch64-linux-gnu/libfuse.so.2",
        "/usr/lib64/libfuse.so.2",
        "/usr/lib/libfuse.so.2",
        "/lib/x86_64-linux-gnu/libfuse.so.2",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    ldconfig = shutil.which("ldconfig")
    if ldconfig:
        import subprocess

        try:
            result = subprocess.run([ldconfig, "-p"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):  # pragma: no cover
            return None
        for line in result.stdout.splitlines():
            if "libfuse.so.2" in line and "=>" in line:
                return line.split("=>", 1)[1].strip()
    return None


def environment_checks() -> list[Check]:
    checks: list[Check] = []

    tool = squashfs.unsquashfs_path()
    checks.append(
        Check(
            OK if tool else FAIL,
            "unsquashfs",
            tool or "not found",
            "" if tool else "install squashfs-tools — without it Appimo must run the bundle to read it",
        )
    )

    dfv = shutil.which("desktop-file-validate")
    checks.append(
        Check(
            OK if dfv else WARN,
            "desktop-file-validate",
            dfv or "not found",
            "" if dfv else "generated launchers will not be validated (install desktop-file-utils)",
        )
    )

    fuse2 = _find_libfuse2()
    fusermount = shutil.which("fusermount3") or shutil.which("fusermount")
    if fuse2 and fusermount:
        checks.append(Check(OK, "FUSE", f"{fuse2} + {Path(fusermount).name}"))
    elif fusermount:
        checks.append(
            Check(
                WARN,
                "FUSE 2",
                "libfuse.so.2 not found",
                "AppImages built before 2023 may refuse to mount; Appimo will offer --extract",
            )
        )
    else:
        checks.append(
            Check(
                WARN,
                "FUSE",
                "no fusermount in PATH",
                "kept AppImages may not launch here; use 'appimo install --extract'",
            )
        )

    for label, directory in (
        ("applications dir", paths.applications_dir()),
        ("icons dir", paths.hicolor_dir()),
        ("apps dir", paths.default_apps_dir()),
    ):
        # These trees usually do not exist yet on a fresh system. Walk up to
        # the nearest existing ancestor rather than calling that a failure.
        probe = directory
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        writable = os.access(probe, os.W_OK)
        checks.append(
            Check(
                OK if writable else FAIL,
                label,
                f"{_pretty(directory)} ({'writable' if writable else 'not writable'})",
                "" if writable else f"cannot write to {_pretty(probe)}",
            )
        )

    if os.geteuid() == 0 and not os.environ.get("APPIMO_ALLOW_ROOT"):
        checks.append(
            Check(
                WARN,
                "running as root",
                "Appimo refuses to install as root",
                "run it as your normal user; launchers must be owned by them",
            )
        )

    state = paths.state_file()
    checks.append(
        Check(
            INFO,
            "inventory",
            f"{_pretty(state)} ({'present' if state.exists() else 'not created yet'})",
        )
    )
    return checks


def bundle_checks(source: Path) -> list[Check]:
    """Per-file checks for a specific bundle."""
    source = source.expanduser()
    checks: list[Check] = []

    if not source.exists():
        return [Check(FAIL, "file", f"no such file: {source}")]

    size = source.stat().st_size
    checks.append(Check(OK, "file", f"{source.name} ({size} bytes)"))

    if source.is_dir():
        has_desktop = any(p.suffix == ".desktop" for p in source.glob("*.desktop"))
        checks.append(
            Check(
                OK if has_desktop else FAIL,
                "AppDir",
                "desktop file present" if has_desktop else "no root .desktop file",
            )
        )
        return checks

    if not os.access(source, os.X_OK):
        checks.append(
            Check(WARN, "executable bit", "not set", f"chmod +x {source}")
        )

    offset = squashfs.scan_offset(source)
    checks.append(
        Check(
            OK if offset is not None else FAIL,
            "squashfs payload",
            f"found at byte {offset}" if offset is not None else "no valid SquashFS superblock",
            "" if offset is not None else "this is probably a type-1 AppImage; try --unsafe-extract",
        )
    )
    return checks


def _pretty(path: Path) -> str:
    home = str(paths.home())
    text = str(path)
    return "~" + text[len(home) :] if text.startswith(home) else text
