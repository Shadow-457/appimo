#!/usr/bin/env python3
"""Generate the Appimo brand assets (SVG + PNG) into assets/logo/.

Design language: flat, sharp corners, no borders, no gradients, one warm
monochrome hue family. Surfaces are dark; the mark is a light square with the
glyph cut out of it in the dark tone.

The wordmark is converted to outlines with fontTools so every asset is
font-independent and renders identically on any machine.

Usage:
    python3 tools/generate-brand-assets.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

# --------------------------------------------------------------------------
# Brand constants — one hue family, deliberately muted.
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "logo"

FONT_REGULAR = Path("/usr/share/fonts/noto/NotoSans-Regular.ttf")
FONT_BOLD = Path("/usr/share/fonts/noto/NotoSans-Bold.ttf")

# The light tone. Text on dark surfaces, and the mark's square.
PAPER = "#E8E3DA"
# The dark tone. Page background, and the glyph inside the square.
INK = "#1A1815"
# Raised and recessed surfaces. Separation comes from tone, never from borders.
SURFACE = "#211E1A"
SURFACE_2 = "#2A2622"
MUTED = "#A39C90"
FAINT = "#8B8478"

# Mark geometry on a 512x512 canvas. No corner radius anywhere: the design
# language is sharp, so the tile, the shaft and the tray are all rectangles.
TILE = 512
TILE_RADIUS = 0
SHAFT = (228, 120, 56, 132)          # x, y, w, h
CHEVRON = "M188 202 L256 270 L324 202"
STROKE = 56
TRAY = (136, 344, 240, 48)           # x, y, w, h
TRAY_OPACITY = 1.0                   # flat: no half-tones on the primary mark
WORDMARK = "appimo"
TAGLINE = "Any AppImage. In your start menu."


# --------------------------------------------------------------------------
# Text -> outlines
# --------------------------------------------------------------------------


class Outliner:
    """Turns a string into a single SVG path using a real font's outlines."""

    def __init__(self, font_path: Path) -> None:
        if not font_path.exists():
            raise SystemExit(f"font not found: {font_path}")
        self.font = TTFont(str(font_path))
        self.glyphset = self.font.getGlyphSet()
        self.upem = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]
        self.cmap = self.font.getBestCmap()

    def _bounds(self, char: str):
        pen = BoundsPen(self.glyphset)
        self.glyphset[self.cmap[ord(char)]].draw(pen)
        return pen.bounds

    def metrics(self, text: str, size: float, tracking: float = 0.0) -> dict:
        """Pixel metrics for `text` rendered at `size` px."""
        scale = size / self.upem
        tops, bottoms, advances = [], [], []
        for char in text:
            bounds = self._bounds(char)
            if bounds:
                tops.append(bounds[3] * scale)
                bottoms.append(bounds[1] * scale)
            advances.append(self.hmtx[self.cmap[ord(char)]][0] * scale)

        width = sum(advances)
        if len(text) > 1:
            width += tracking * size * (len(text) - 1)
        xheight = self._bounds("x")[3] * scale

        return {
            "width": width,
            "x_height": xheight,
            "top": max(tops) if tops else 0.0,      # above baseline (px)
            "bottom": min(bottoms) if bottoms else 0.0,  # below baseline (negative px)
        }

    def path(self, text: str, size: float, x: float, baseline: float,
             tracking: float = 0.0) -> str:
        """SVG path data for `text`, drawn with its baseline at `baseline`."""
        scale = size / self.upem
        cursor = x
        commands: list[str] = []
        for char in text:
            name = self.cmap[ord(char)]
            pen = SVGPathPen(self.glyphset, ntos=lambda v: f"{v:.2f}")
            self.glyphset[name].draw(
                TransformPen(pen, (scale, 0, 0, -scale, cursor, baseline))
            )
            data = pen.getCommands()
            if data:
                commands.append(data)
            cursor += self.hmtx[name][0] * scale + tracking * size
        return " ".join(commands)


# --------------------------------------------------------------------------
# Mark
# --------------------------------------------------------------------------


def glyph(color: str, tray_opacity: float = TRAY_OPACITY) -> str:
    """The Appimo glyph: an AppImage dropping onto the menu shelf.

    Square ends and a mitred join — flat, matching the sharp-cornered design.
    """
    x, y, w, h = SHAFT
    tx, ty, tw, th = TRAY
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>'
        f'<path d="{CHEVRON}" fill="none" stroke="{color}" stroke-width="{STROKE}"'
        ' stroke-linecap="square" stroke-linejoin="miter"/>'
        f'<rect x="{tx}" y="{ty}" width="{tw}" height="{th}"'
        f' fill="{color}" fill-opacity="{tray_opacity}"/>'
    )


def svg(body: str, width: float, height: float, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}"'
        f' width="{width:g}" height="{height:g}" role="img"'
        f' aria-label="{title}">\n  <title>{title}</title>\n{body}\n</svg>\n'
    )


def mark_tone(square: str, glyph_color: str) -> str:
    """Flat, sharp-cornered mark: a solid square with the glyph in the other tone."""
    body = (
        f'  <rect width="{TILE}" height="{TILE}" rx="{TILE_RADIUS}"'
        f' fill="{square}"/>\n'
        f'  {glyph(glyph_color)}'
    )
    return svg(body, TILE, TILE, "Appimo")


def mark_svg() -> str:
    """For dark surfaces: a paper square with the glyph in the dark tone."""
    return mark_tone(PAPER, INK)


def mark_dark_svg() -> str:
    """For light surfaces: the inverse."""
    return mark_tone(INK, PAPER)


def mark_mono_svg() -> str:
    """currentColor throughout, glyph knocked out. For inlining in HTML."""
    body = (
        '  <defs>\n'
        '    <mask id="appimo-knockout">\n'
        f'      <rect width="{TILE}" height="{TILE}" rx="{TILE_RADIUS}" fill="#fff"/>\n'
        '      ' + glyph("#000", 1.0) + '\n'
        '    </mask>\n'
        '  </defs>\n'
        f'  <rect width="{TILE}" height="{TILE}" rx="{TILE_RADIUS}"'
        ' fill="currentColor" mask="url(#appimo-knockout)"/>'
    )
    return svg(body, TILE, TILE, "Appimo")


def glyph_svg() -> str:
    return svg("  " + glyph("currentColor", 1.0), TILE, TILE, "Appimo")


# --------------------------------------------------------------------------
# Lockups
# --------------------------------------------------------------------------

MARK_IN_LOCKUP = 112
GAP = 30
WORD_SIZE = 78
LETTER_TRACKING = -0.015


def lockup_svg(bold: Outliner, *, on_dark: bool) -> tuple[str, float]:
    """Horizontal lockup: mark + wordmark, in one tone for one background."""
    square = PAPER if on_dark else INK
    ink = INK if on_dark else PAPER
    text = PAPER if on_dark else INK

    metrics = bold.metrics(WORDMARK, WORD_SIZE, LETTER_TRACKING)
    baseline = MARK_IN_LOCKUP / 2 + metrics["x_height"] / 2
    path = bold.path(WORDMARK, WORD_SIZE, GAP + MARK_IN_LOCKUP, baseline,
                     LETTER_TRACKING)
    width = round(GAP + MARK_IN_LOCKUP + metrics["width"] + 6)
    scale = MARK_IN_LOCKUP / TILE

    body = (
        f'  <g transform="scale({scale:.5f})">\n'
        f'    <rect width="{TILE}" height="{TILE}" rx="{TILE_RADIUS}"'
        f' fill="{square}"/>\n'
        f'    {glyph(ink)}\n'
        '  </g>\n'
        f'  <path d="{path}" fill="{text}"/>'
    )
    return svg(body, width, MARK_IN_LOCKUP, "Appimo"), width


def wordmark_svg(bold: Outliner, color: str) -> str:
    metrics = bold.metrics(WORDMARK, WORD_SIZE, LETTER_TRACKING)
    baseline = metrics["top"]
    height = metrics["top"] - metrics["bottom"]
    path = bold.path(WORDMARK, WORD_SIZE, 0, baseline, LETTER_TRACKING)
    return svg(f'  <path d="{path}" fill="{color}"/>',
               round(metrics["width"]), round(height), "appimo")


# --------------------------------------------------------------------------
# Social / OG banner
# --------------------------------------------------------------------------

BANNER_W, BANNER_H = 1200, 630


def banner_svg(bold: Outliner, regular: Outliner) -> str:
    """Flat: one background tone, one surface tone, no gradients or glows."""
    mark = 132
    word = 92
    metrics = bold.metrics(WORDMARK, word, LETTER_TRACKING)
    word_path = bold.path(WORDMARK, word, mark + GAP, 0, LETTER_TRACKING)
    lock_w = mark + GAP + metrics["width"]

    tag_metrics = regular.metrics(TAGLINE, 34)
    tag_path = regular.path(TAGLINE, 34, 0, 0)

    cx = (BANNER_W - lock_w) / 2
    lock_top = 236

    scale = mark / TILE
    tiles = []
    for row in range(10):
        for col in range(19):
            tiles.append(
                f'<rect x="{18 + col * 64}" y="{18 + row * 64}" width="42"'
                f' height="42" fill="{PAPER}" fill-opacity="0.035"/>'
            )

    body = (
        f'  <rect width="{BANNER_W}" height="{BANNER_H}" fill="{INK}"/>\n'
        '  <g>' + "".join(tiles) + '</g>\n'
        f'  <g transform="translate({cx:g} {lock_top})">\n'
        f'    <g transform="scale({scale:.5f})">\n'
        f'      <rect width="{TILE}" height="{TILE}" rx="{TILE_RADIUS}"'
        f' fill="{PAPER}"/>\n'
        f'      {glyph(INK)}\n'
        '    </g>\n'
        f'    <path d="{word_path}" fill="{PAPER}"/>\n'
        '  </g>\n'
        f'  <g transform="translate({(BANNER_W - tag_metrics["width"]) / 2:g} 470)">\n'
        f'    <path d="{tag_path}" fill="{PAPER}" fill-opacity="0.6"/>\n'
        '  </g>'
    )
    return svg(body, BANNER_W, BANNER_H, "Appimo")


# --------------------------------------------------------------------------
# Raster export
# --------------------------------------------------------------------------

ICON_SIZES = (16, 24, 32, 48, 64, 128, 180, 256, 512, 1024)


def rasterize(source: Path, target: Path, width: int, height: int) -> bool:
    if shutil.which("rsvg-convert"):
        result = subprocess.run(
            ["rsvg-convert", "-w", str(width), "-h", str(height),
             "-o", str(target), str(source)],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    try:
        import cairosvg
        cairosvg.svg2png(url=str(source), write_to=str(target),
                         output_width=width, output_height=height)
        return True
    except ImportError:
        return False


def main() -> int:
    if not FONT_BOLD.exists():
        print(f"! bold font missing: {FONT_BOLD}", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    bold = Outliner(FONT_BOLD)
    regular = Outliner(FONT_REGULAR)

    for_dark, lock_w = lockup_svg(bold, on_dark=True)
    for_light, _ = lockup_svg(bold, on_dark=False)

    svgs = {
        "appimo-mark.svg": mark_svg(),
        "appimo-mark-dark.svg": mark_dark_svg(),
        "appimo-mark-mono.svg": mark_mono_svg(),
        "appimo-glyph.svg": glyph_svg(),
        "appimo-wordmark.svg": wordmark_svg(bold, PAPER),
        "appimo-logo.svg": for_light,
        "appimo-logo-light.svg": for_dark,
        "appimo-banner.svg": banner_svg(bold, regular),
        "favicon.svg": mark_svg(),
    }
    for name, content in svgs.items():
        (OUT / name).write_text(content, encoding="utf-8")
        print(f"  svg  {name}")

    mark_src = OUT / "appimo-mark.svg"
    for size in ICON_SIZES:
        target = OUT / f"appimo-icon-{size}.png"
        if rasterize(mark_src, target, size, size):
            print(f"  png  {target.name}")
        else:
            print(f"! could not rasterise {target.name}", file=sys.stderr)

    for name, src, width in (
        ("appimo-logo.png", OUT / "appimo-logo.svg", round(lock_w * 4)),
        ("appimo-banner.png", OUT / "appimo-banner.svg", BANNER_W),
    ):
        height = round(width * (MARK_IN_LOCKUP / lock_w)) if "logo" in name else BANNER_H
        if rasterize(src, OUT / name, width, height):
            print(f"  png  {name}")

    if shutil.which("magick"):
        ico = OUT / "favicon.ico"
        subprocess.run(
            ["magick", str(OUT / "appimo-icon-256.png"),
             "-define", "icon:auto-resize=64,48,32,24,16", str(ico)],
            capture_output=True,
        )
        print("  ico  favicon.ico")

    print(f"\nwrote assets to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
