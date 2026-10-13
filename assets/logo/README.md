# Appimo brand assets

The Appimo logo system. Every file here is generated from code — edit
[`tools/generate-brand-assets.py`](../../tools/generate-brand-assets.py) and re-run it
rather than hand-editing an SVG, or your change will be overwritten on the next run.

```bash
python3 tools/generate-brand-assets.py
```

Requires `fontTools` (the wordmark is converted to outlines, so no font has to be
installed to render it) and one of `rsvg-convert` or `cairosvg` for the PNG exports.

## The mark

An AppImage (the round-capped arrow) dropping onto the menu shelf (the tray bar) —
the whole product in one gesture: *a loose file becomes a real app in your start menu.*

The wordmark is lowercase `appimo`, outlined from Noto Sans Bold with tightened
tracking (`-0.015em`).

## Files

| File | Use |
| --- | --- |
| `appimo-mark.svg` | The icon. Primary use everywhere. |
| `appimo-mark-mono.svg` | `currentColor` tile with the glyph knocked out. Footers, print, monochrome UI. |
| `appimo-glyph.svg` | Tile-less glyph in `currentColor`. Inline in a nav bar or a terminal-rendered UI. |
| `appimo-wordmark.svg` | Wordmark alone, ink colour. |
| `appimo-logo.svg` | Horizontal lockup, ink wordmark. Light backgrounds. |
| `appimo-logo-light.svg` | Horizontal lockup, white wordmark. Dark backgrounds. |
| `appimo-logo.png` | Raster lockup at 1744 px wide. Press, slide decks. |
| `appimo-banner.svg` / `.png` | 1200×630 social + Open Graph card. |
| `appimo-icon-{16,24,32,48,64,128,180,256,512,1024}.png` | App icon, favicon, PWA/PyPI/AppImage sizes. |
| `favicon.svg` / `favicon.ico` | Browser tabs (`.ico` carries 16/24/32/48/64). |

All files are tight-cropped to their content. Add your own margin — don't scale
the mark below 16 px, and keep at least 25% of the mark's width as clear space.

## Colour

| Role | Hex | Notes |
| --- | --- | --- |
| Gradient start (violet) | `#5334DE` | Tile, top-left → bottom-right |
| Gradient end (blue) | `#1B45C4` | Diagonal, `objectBoundingBox` |
| Accent (electric cyan) | `#22D3EE` | Highlights, links and glows on dark surfaces — never behind the white glyph |
| Ink | `#0B1020` | Body text, dark backgrounds |
| Slate | `#5A6178` | Secondary text |
| Cloud | `#F4F6FB` | Light page background |
| White | `#FFFFFF` | Glyph, text on the tile |

The gradient is deliberately deep and near-constant in luminance: the violet and
blue ends both sit around `L*70`, so the white glyph holds **3.4:1** contrast
(WCAG 1.4.11 wants 3:1) and stays legible at 16 px. Do not brighten it toward
cyan behind the glyph — that was measured at 2.2:1 and it fell apart at favicon
size. The cyan is a surface accent only.

Contrast was verified by rendering each size and sampling the tile, arrow and
tray pixels; re-run that check if you change the gradient.

## Usage rules

**Do** keep the mark square and unrotated, use the mono variant on photography or
busy backgrounds, and pick `appimo-logo.svg` / `appimo-logo-light.svg` by the
background.

**Don't** recolour the gradient, add shadows or outlines, stretch the mark, put
the white-glyph mark on a light background, or set the wordmark in a different
font. Don't crop the tile into anything but its rounded square.

## Licensing

The Appimo name and logo belong to the project. The code is GPL-3.0 (see
[`../../Copyright`](../../Copyright)); GPL-3.0 does **not** automatically grant
trademark rights to the name or mark.
