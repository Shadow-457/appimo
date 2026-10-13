"""The SquashFS offset scanner and reader.

The important property under test is that a plausible-looking `hsqs` byte
sequence inside a bundle's runtime is *not* mistaken for the filesystem.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from appimo import squashfs

from conftest import build_appdir, build_bundle, squashfs_available

pytestmark = pytest.mark.skipif(not squashfs_available(), reason="mksquashfs is not installed")


def test_scan_finds_payload_after_an_elf_prefix(tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir")
    bundle = build_bundle(appdir, tmp_path / "Demo.AppImage", prefix_elf=True)
    offset = squashfs.scan_offset(bundle)
    # The fixture's prefix is 4 + 4092 + 4 + 64 + 28 bytes.
    assert offset == 4 + 4092 + 4 + 64 + 28
    assert squashfs.scan_offset(bundle) is not None


def test_scan_finds_a_bare_squashfs_at_zero(tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir")
    plain = build_bundle(appdir, tmp_path / "plain.squashfs", prefix_elf=False)
    assert squashfs.scan_offset(plain) == 0


def test_scan_ignores_random_data(tmp_path: Path) -> None:
    junk = tmp_path / "junk.bin"
    junk.write_bytes(bytes(range(256)) * 32)
    assert squashfs.scan_offset(junk) is None


def test_scan_rejects_a_bare_magic_without_a_valid_superblock(tmp_path: Path) -> None:
    fake = tmp_path / "fake.bin"
    fake.write_bytes(b"ELF padding" + b"hsqs" + b"\xff" * 200)
    assert squashfs.scan_offset(fake) is None


def test_scan_rejects_a_plausible_but_truncated_superblock(tmp_path: Path) -> None:
    """Correct magic and version, but the declared size runs past the file."""
    superblock = struct.pack(
        "<4sIIIIHHHHHHQQQ",
        b"hsqs",  # magic
        10,  # inode_count
        0,  # mtime
        131072,  # block_size
        0,  # fragment count
        1,  # compression: gzip
        17,  # block_log
        0,  # flags
        1,  # id_count
        4,  # version major
        0,  # version minor
        0,  # root inode ref
        999_999,  # bytes_used: far bigger than the file
        0,  # id table start
    )
    truncated = tmp_path / "truncated.bin"
    truncated.write_bytes(b"\x00" * 64 + superblock)
    assert squashfs.scan_offset(truncated) is None


def test_scan_handles_trailing_bytes_after_the_filesystem(tmp_path: Path) -> None:
    """Trailing padding breaks the exact-fit check; the real payload still wins."""
    appdir = build_appdir(tmp_path / "AppDir")
    plain = build_bundle(appdir, tmp_path / "plain.squashfs", prefix_elf=False)
    padded = tmp_path / "padded.squashfs"
    padded.write_bytes(plain.read_bytes() + b"\x00" * 512)
    assert squashfs.scan_offset(padded) == 0


def test_list_and_read_members(tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir")
    bundle = build_bundle(appdir, tmp_path / "Demo.AppImage")

    members = squashfs.list_members(bundle, squashfs.scan_offset(bundle))
    assert "demo.desktop" in members
    assert "AppRun" in members
    assert "demo.png" in members
    # Directories are members too, and must come back without the root prefix.
    assert "usr/share/icons" in members
    assert not any(m.startswith("squashfs-root") for m in members)

    data = squashfs.read_member(bundle, squashfs.scan_offset(bundle), "demo.desktop")
    assert data is not None
    assert b"Name=Demo App" in data


def test_symlink_members_come_back_without_their_target(tmp_path: Path) -> None:
    """Real AppImages make .DirIcon a symlink; `-ll` prints `link -> target`
    as one field, and that arrow must never leak into a member path — or the
    icon read asks for a file that doesn't exist."""
    appdir = build_appdir(tmp_path / "AppDir", icon_location="hicolor")
    (appdir / ".DirIcon").symlink_to("usr/share/icons/hicolor/256x256/apps/demo.png")
    bundle = build_bundle(appdir, tmp_path / "Demo.AppImage")
    offset = squashfs.scan_offset(bundle)

    members = squashfs.list_members(bundle, offset)
    assert ".DirIcon" in members
    assert not any(" -> " in m for m in members)

    icon = squashfs.read_member(bundle, offset, ".DirIcon")
    assert icon is not None
    assert icon[:8] == b"\x89PNG\r\n\x1a\n"


def test_read_member_returns_none_when_absent(tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir")
    bundle = build_bundle(appdir, tmp_path / "Demo.AppImage")
    assert squashfs.read_member(bundle, squashfs.scan_offset(bundle), "nope.txt") is None


def test_extract_all_materialises_the_tree(tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir")
    bundle = build_bundle(appdir, tmp_path / "Demo.AppImage")
    dest = tmp_path / "out"
    squashfs.extract_all(bundle, squashfs.scan_offset(bundle), dest)
    assert (dest / "demo.desktop").exists()
    assert (dest / "AppRun").exists()


def test_missing_unsquashfs_is_reported_clearly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(squashfs, "unsquashfs_path", lambda: None)
    with pytest.raises(squashfs.UnreadableBundle):
        squashfs.list_members(tmp_path / "x", 0)
