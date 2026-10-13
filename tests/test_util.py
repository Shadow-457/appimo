"""Naming, Exec quoting and image sniffing."""

from __future__ import annotations

import pytest

from appimo.util import (
    build_exec,
    collapse_whitespace,
    human_bytes,
    image_kind,
    is_svg,
    png_size,
    quote_exec_arg,
    shorten_path,
    slugify,
    split_exec,
)

from conftest import make_png


@pytest.mark.parametrize(
    "value,expected",
    [
        ("GNOME Boxes", "gnome-boxes"),
        ("Cursor 0.45", "cursor-0-45"),
        ("  spaced  out  ", "spaced-out"),
        ("Ünïcödé", "n-c-d"),
        ("...", "app"),
        ("", "app"),
        ("firefox", "firefox"),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


@pytest.mark.parametrize(
    "arg,expected",
    [
        ("simple", "simple"),
        ("/plain/path", "/plain/path"),
        ("/has space/app", '"/has space/app"'),
        ("/has$dollar", '"/has\\$dollar"'),
        ('/has"quote', '"/has\\"quote"'),
        ("/has\\backslash", '"/has\\\\backslash"'),
        ("/has`tick", '"/has\\`tick"'),
        ("/semi;colon", '"/semi;colon"'),
    ],
)
def test_quote_exec_arg(arg: str, expected: str) -> None:
    assert quote_exec_arg(arg) == expected


@pytest.mark.parametrize(
    "value",
    [
        '/home/me/Applications/Demo App.AppImage %U',
        '/opt/x %F --flag=value',
        '"/path with spaces/app" %U',
        'plain',
        '/path/with\\\\backslash tail',
    ],
)
def test_split_exec_round_trips_through_build_exec(value: str) -> None:
    command, arguments = split_exec(value)
    assert split_exec(build_exec(command, arguments)) == (command, arguments)


def test_split_exec_separates_the_command_from_field_codes() -> None:
    assert split_exec('"/a b/c" %U') == ("/a b/c", ["%U"])
    assert split_exec("demo %U --quiet") == ("demo", ["%U", "--quiet"])
    assert split_exec("") == ("", [])


def test_build_exec_quotes_only_what_needs_it() -> None:
    assert build_exec("/usr/bin/demo", ["%U"]) == "/usr/bin/demo %U"
    assert build_exec("/opt/My App/bin", ["%U"]) == '"/opt/My App/bin" %U'


def test_png_size_reads_real_dimensions() -> None:
    assert png_size(make_png(32, 16)) == (32, 16)
    assert png_size(make_png(256, 256)) == (256, 256)


def test_png_size_rejects_non_png() -> None:
    assert png_size(b"not a png at all") is None
    assert png_size(b"") is None
    assert png_size(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40) is None


def test_is_svg_and_image_kind() -> None:
    assert is_svg(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert is_svg(b'\xef\xbb\xbf<?xml version="1.0"?><svg/>')
    assert not is_svg(b"\x89PNG")
    assert image_kind(make_png(4, 4)) == "png"
    assert image_kind(b"<svg/>") == "svg"
    assert image_kind(b"/* XPM */") == "xpm"
    assert image_kind(b"random") is None


def test_human_bytes_and_shorten_path() -> None:
    assert human_bytes(512) == "512 B"
    assert human_bytes(2048) == "2.0 KiB"
    assert shorten_path("/short") == "/short"
    assert shorten_path("/" + "a" * 100).startswith("…")


def test_collapse_whitespace() -> None:
    assert collapse_whitespace("  a   b \n c ") == "a b c"
