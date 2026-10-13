"""Shared test fixtures.

Every test that installs anything runs against a sandboxed HOME, so the suite
can never touch the developer's real `~/.local` or `~/Applications`.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

DESKTOP = """[Desktop Entry]
Type=Application
Name={name}
Comment={comment}
Exec=demo %U
Icon={icon}
Categories=Utility;Development;
Terminal=false
MimeType=text/plain;
"""


def make_png(width: int, height: int, rgba: tuple[int, int, int, int] = (255, 90, 0, 255)) -> bytes:
    """A real, valid PNG of any size, built with the standard library only."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def build_appdir(
    root: Path,
    *,
    name: str = "Demo App",
    comment: str = "A demo application",
    icon: str = "demo",
    icon_size: int = 256,
    icon_location: str = "root",
    app_run: bool = True,
) -> Path:
    """Create an AppDir on disk. `icon_location` is root, .DirIcon or hicolor."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "usr" / "share" / "icons" / "hicolor" / f"{icon_size}x{icon_size}" / "apps").mkdir(
        parents=True, exist_ok=True
    )
    png = make_png(icon_size, icon_size)

    (root / "demo.desktop").write_text(
        DESKTOP.format(name=name, comment=comment, icon=icon), encoding="utf-8"
    )
    if app_run:
        apprun = root / "AppRun"
        apprun.write_text("#!/bin/sh\necho demo\n", encoding="utf-8")
        apprun.chmod(0o755)

    if icon_location == "root":
        (root / f"{icon}.png").write_bytes(png)
    elif icon_location == ".DirIcon":
        (root / ".DirIcon").write_bytes(png)
    elif icon_location == "hicolor":
        (root / "usr/share/icons/hicolor" / f"{icon_size}x{icon_size}" / "apps" / f"{icon}.png").write_bytes(png)
    return root


def squashfs_available() -> bool:
    return shutil.which("mksquashfs") is not None


def build_bundle(root: Path, dest: Path, *, prefix_elf: bool = True) -> Path:
    """Squash an AppDir and optionally prepend an ELF header, like a real AppImage."""
    if not squashfs_available():
        pytest.skip("mksquashfs is not installed")
    plain = dest.with_suffix(".fs")
    subprocess.run(
        ["mksquashfs", str(root), str(plain), "-root-owned", "-noappend", "-quiet"],
        check=True,
        capture_output=True,
    )
    payload = plain.read_bytes()
    if prefix_elf:
        # A stand-in for the AppImage runtime: enough to look like an ELF and
        # to prove the offset scan is not confused by bytes inside it.
        prefix = b"\x7fELF" + b"\x00" * 4092 + b"hsqs" + b"\xff" * 64
        header = struct.pack(">I", 0) + b"\x00" * 24
        (dest).write_bytes(prefix + header + payload)
    else:
        dest.write_bytes(payload)
    dest.chmod(0o755)
    plain.unlink()
    return dest


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME with every XDG path redirected into it."""
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("APPIMO_APPS_DIR", str(home / "Applications"))
    monkeypatch.delenv("APPIMO_ALLOW_ROOT", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    return home


@pytest.fixture
def appdir(tmp_path: Path) -> Path:
    return build_appdir(tmp_path / "AppDir")


@pytest.fixture
def bundle(tmp_path: Path, appdir: Path) -> Path:
    return build_bundle(appdir, tmp_path / "Demo.AppImage")


@pytest.fixture
def real_appimage() -> Path:
    """A genuine AppImage, when the developer points at one.

    Set APPIMO_TEST_APPIMAGE=/path/to/File.AppImage to also exercise the suite
    against a real bundle produced by the AppImage tooling.
    """
    raw = os.environ.get("APPIMO_TEST_APPIMAGE")
    if not raw:
        pytest.skip("set APPIMO_TEST_APPIMAGE to test against a real AppImage")
    path = Path(raw)
    if not path.exists():
        pytest.skip(f"APPIMO_TEST_APPIMAGE does not exist: {path}")
    return path
