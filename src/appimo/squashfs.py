"""Read a bundle's SquashFS payload without executing it.

This is the part of Appimo that most differs from the tools that came before.
AppImageLauncher, appimaged and friends ask the AppImage to describe itself by
running its runtime (`./App.AppImage --appimage-extract`). That means executing
a file you just downloaded from the internet before you know what it is.

An AppImage is an ELF runtime with a SquashFS filesystem appended. We locate
that filesystem by scanning for its superblock and validating the header, then
read members with `unsquashfs -o <offset>`. Executing the bundle is only used
as a last-resort fallback when `unsquashfs` is unavailable.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from .errors import UnreadableBundle

#: SquashFS superblock magic, in on-disk byte order.
SQUASHFS_MAGIC = b"hsqs"

#: Little-endian superblock up to `id_table_start`.
_SUPERBLOCK = struct.Struct("<4sIIIIHHHHHHQQQ")

#: compression ids 1..6 are gzip, lzma, lzo, xz, lz4, zstd.
_MAX_COMPRESSION_ID = 6

_SQFS_ENTRY = re.compile(r"^[-dlbcps][rwxsStT-]{9}\s")
_KIB = 1024


def unsquashfs_path() -> str | None:
    """Path to `unsquashfs`, if the system has squashfs-tools."""
    return shutil.which("unsquashfs")


def _looks_like_superblock(data: bytes, offset: int, file_size: int) -> int | None:
    """Validate a candidate superblock and return its `bytes_used`, or None.

    Validating is essential: the four bytes `hsqs` occur by chance inside the
    runtime ELF (and inside compressed data), so a bare magic search finds
    false positives. We check the header fields *and* that the declared size
    lands exactly on the end of the file.
    """
    if offset + _SUPERBLOCK.size > file_size:
        return None
    (
        magic,
        inode_count,
        _mtime,
        block_size,
        _fragments,
        compression_id,
        _block_log,
        _flags,
        _id_count,
        version_major,
        version_minor,
        _root_inode,
        bytes_used,
        _id_table_start,
    ) = _SUPERBLOCK.unpack_from(data, offset)

    if magic != SQUASHFS_MAGIC:
        return None
    if (version_major, version_minor) != (4, 0):
        return None
    if inode_count == 0:
        return None
    if compression_id == 0 or compression_id > _MAX_COMPRESSION_ID:
        return None
    # SquashFS block size must be a power of two between 4 KiB and 1 MiB.
    if block_size < 4 * _KIB or block_size > 1024 * _KIB:
        return None
    if block_size & (block_size - 1):
        return None
    if bytes_used == 0 or offset + bytes_used > file_size:
        return None
    return bytes_used


def scan_offset(image: Path) -> int | None:
    """Byte offset of the embedded SquashFS, or None if there isn't one.

    Works for a type-2 AppImage (payload appended after the runtime), a bare
    `.squashfs` file (offset 0), and anything else with a filesystem appended.
    """
    size = image.stat().st_size
    if size < _SUPERBLOCK.size:
        return None

    with image.open("rb") as handle:
        blob = handle.read()

    exact: int | None = None
    best: tuple[int, int] | None = None  # (offset, bytes_used)
    start = 0
    while True:
        found = blob.find(SQUASHFS_MAGIC, start)
        if found < 0:
            break
        start = found + 1
        bytes_used = _looks_like_superblock(blob, found, size)
        if bytes_used is None:
            continue
        if found + bytes_used == size:
            exact = found  # a perfect fit: the payload ends with the file
        elif best is None or found > best[0]:
            best = (found, bytes_used)

    if exact is not None:
        return exact
    return best[0] if best else None


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(argv, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - environment
        raise UnreadableBundle(
            f"reading the bundle timed out after {timeout}s",
            hint="the file may be corrupt or on a very slow mount",
        ) from exc


def list_members(image: Path, offset: int, timeout: int = 120) -> list[str]:
    """Every member path inside the SquashFS, without the `squashfs-root/` prefix."""
    tool = unsquashfs_path()
    if not tool:
        raise UnreadableBundle(
            "unsquashfs is not installed, so the bundle cannot be read safely",
            hint="install squashfs-tools (or run with --unsafe-extract)",
        )
    result = _run([tool, "-o", str(offset), "-ll", str(image)], timeout)
    if result.returncode != 0:
        raise UnreadableBundle(
            f"unsquashfs could not read {image.name}",
            hint=result.stderr.decode("utf-8", "replace").strip().splitlines()[-1]
            if result.stderr.strip()
            else None,
        )

    members: list[str] = []
    for raw in result.stdout.decode("utf-8", "replace").splitlines():
        line = raw.rstrip()
        if not _SQFS_ENTRY.match(line):
            continue
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        path = fields[5]
        # Symlink lines carry their target in the same field:
        # `squashfs-root/.DirIcon -> usr/share/icons/...`. The member is the
        # path alone; `-cat` follows the link when reading it.
        if " -> " in path:
            path = path.split(" -> ", 1)[0]
        if path.startswith("squashfs-root/"):
            path = path[len("squashfs-root/") :]
        elif path == "squashfs-root":
            continue
        members.append(path)
    return members


def read_member(image: Path, offset: int, member: str, timeout: int = 120) -> bytes | None:
    """Read one file out of the SquashFS, or None if it isn't there."""
    tool = unsquashfs_path()
    if not tool:
        raise UnreadableBundle(
            "unsquashfs is not installed, so the bundle cannot be read safely",
            hint="install squashfs-tools",
        )
    if " -> " in member:  # a symlink line handed over unsplit
        member = member.split(" -> ", 1)[0]
    result = _run([tool, "-o", str(offset), "-cat", str(image), member], timeout)
    if result.returncode != 0:
        return None
    return result.stdout


def extract_all(image: Path, offset: int, dest: Path, timeout: int = 900) -> Path:
    """Extract the whole filesystem into `dest` and return the AppDir root."""
    tool = unsquashfs_path()
    if not tool:
        raise UnreadableBundle("unsquashfs is not installed", hint="install squashfs-tools")
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [tool, "-o", str(offset), "-no-progress", "-f", "-d", str(dest), str(image)],
        timeout,
    )
    if result.returncode != 0:
        raise UnreadableBundle(
            f"could not extract {image.name}",
            hint=result.stderr.decode("utf-8", "replace").strip().splitlines()[-1]
            if result.stderr.strip()
            else None,
        )
    return dest
