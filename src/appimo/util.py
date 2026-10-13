"""Small helpers shared across Appimo: naming, Exec quoting, image sniffing."""

from __future__ import annotations

import re
import struct

_WS = re.compile(r"\s+")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# Characters that force an Exec argument to be quoted. From the Desktop Entry
# Specification, "Quoting" section.
_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def slugify(value: str) -> str:
    """A filesystem- and id-safe slug: `GNOME Boxes 2.0` -> `gnome-boxes-2-0`."""
    text = _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")
    return text or "app"


def quote_exec_arg(arg: str) -> str:
    """Quote one argument for a `Exec=` line.

    This is *not* shell quoting — the desktop entry spec defines its own rules
    (double quotes, and only `"`, backtick, `$` and `\\` escaped).
    """
    if not any(char in _RESERVED for char in arg):
        return arg
    escaped = (
        arg.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def build_exec(command: str, arguments: list[str]) -> str:
    """Build an `Exec=` value: an absolute command plus preserved arguments."""
    parts = [quote_exec_arg(command), *(quote_exec_arg(a) for a in arguments)]
    return " ".join(parts)


def split_exec(value: str) -> tuple[str, list[str]]:
    """Split an `Exec=` value into its command and its remaining arguments.

    Handles the spec's quoting so `"/opt/My App" %U` splits correctly. Returns
    the command and the trailing arguments (including any `%f`/`%u` field
    codes) so the caller can preserve flags the application expects.
    """
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    escaped = False
    for char in value.strip():
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quotes = not in_quotes
            continue
        if char.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    if not tokens:
        return "", []
    return tokens[0], tokens[1:]


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int] | None:
    """Read width/height from a PNG header, or None if it isn't a PNG."""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE):
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def is_svg(data: bytes) -> bool:
    """Best-effort SVG sniff, tolerant of a leading BOM or XML comment."""
    head = data[:512].lstrip(b"\xef\xbb\xbf").lstrip()
    return head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head)


def image_kind(data: bytes) -> str | None:
    """`png`, `svg`, `xpm` or None for the formats the icon spec allows."""
    if png_size(data):
        return "png"
    if is_svg(data):
        return "svg"
    if data[:9] == b"/* XPM */":
        return "xpm"
    return None


def human_bytes(count: int) -> str:
    """`1536` -> `1.5 KiB`."""
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def shorten_path(path: str, limit: int = 42) -> str:
    """`/home/x/Downloads/really-long-name.AppImage` -> `…/really-long-name.AppImage`."""
    if len(path) <= limit:
        return path
    return "…" + path[-(limit - 1) :]


def collapse_whitespace(value: str) -> str:
    return _WS.sub(" ", value).strip()
