"""The Flet interface for Appimo.

Built for Flet 1.0 (controls are dataclasses, `FilePicker` methods are async,
the entry point is `ft.run`).

The window shows the plan before it applies it, because "what is this about to
change?" is the question a tool that writes launchers into your home directory
has to answer up front.

Visual language matches the site: flat, sharp corners, no borders, no shadows,
one warm monochrome hue family on dark surfaces. Separation comes from tone
steps (`BG` -> `SURFACE` -> `SURFACE_2`), never from outlines.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from .. import __version__, paths
from ..errors import AppimoError
from ..installer import (
    MODE_EXTRACT,
    MODE_KEEP,
    InstallOptions,
    apply_install,
    apply_remove,
    plan_install,
    plan_remove,
)
from ..state import State

# The palette, shared with landing/styles.css and tools/generate-brand-assets.py.
BG = "#1A1815"
SURFACE = "#211E1A"
SURFACE_2 = "#2A2622"
PAPER = "#E8E3DA"
MUTED = "#A39C90"
FAINT = "#8B8478"

#: Path of the mark *relative to assets_dir*. Flet only serves files that live
#: under `assets_dir`, so an absolute filesystem path would silently 404.
LOGO_RELATIVE = "logo/appimo-icon-256.png"

#: The app's typeface, bundled under assets/fonts/. The site's stack resolves
#: to Noto Sans on most Linux desktops, so the app uses the real thing — the
#: same face everywhere, installed or not.
FONT_FAMILY = "Noto Sans"
FONT_FILES = {
    FONT_FAMILY: "fonts/NotoSans-Regular.ttf",
    f"{FONT_FAMILY} Medium": "fonts/NotoSans-Medium.ttf",
    f"{FONT_FAMILY} Bold": "fonts/NotoSans-Bold.ttf",
}


def assets_root() -> Path | None:
    """The checkout's `assets/` directory, when running from a source tree."""
    candidates = (
        Path(__file__).resolve().parents[3] / "assets",
        Path.cwd() / "assets",
    )
    for candidate in candidates:
        if (candidate / LOGO_RELATIVE).exists():
            return candidate
    return None


def _logo_src() -> str | None:
    """The mark to display, or None when it isn't available (installed wheel)."""
    return LOGO_RELATIVE if assets_root() else None


def _pretty(path: str | Path) -> str:
    text = str(path)
    home = str(paths.home())
    return "~" + text[len(home) :] if text.startswith(home) else text


def _set_window(page, width: int, height: int) -> None:
    """Flet renamed the window API between versions; try both, quietly."""
    for setter in (
        lambda: setattr(page.window, "width", width),
        lambda: setattr(page.window, "height", height),
        lambda: setattr(page, "window_width", width),
        lambda: setattr(page, "window_height", height),
    ):
        try:
            setter()
        except Exception:  # pragma: no cover - version differences
            pass


def _apply_theme(page) -> None:
    """Force Material's own controls to follow the flat monochrome language.

    Without this, stock widgets leak their defaults: a blue accent on the
    switch, rounded snackbar corners, a round scrollbar thumb. Every field is
    set inside one try/except because Flet reshuffles these themes between
    releases — a wrong field name must cost nothing.
    """
    ft = page.ft if hasattr(page, "ft") else None
    if ft is None:
        import flet as _ft
        ft = _ft

    try:
        # The bundled Noto Sans faces, when running from a checkout that has
        # them. Without an assets dir (installed wheel) Flutter's default
        # stays in force, which is close enough not to matter.
        root = assets_root()
        if root and (root / "fonts/NotoSans-Regular.ttf").exists():
            page.fonts = {
                family: f"/{relative}" for family, relative in FONT_FILES.items()
            }
        page.theme = ft.Theme(
            font_family=FONT_FAMILY,
            color_scheme=ft.ColorScheme(
                primary=PAPER,
                on_primary=BG,
                secondary=PAPER,
                on_secondary=BG,
                surface=BG,
                on_surface=PAPER,
                on_surface_variant=MUTED,
                outline=SURFACE_2,
                outline_variant=SURFACE_2,
                surface_tint=SURFACE,
                error=PAPER,
                on_error=BG,
            ),
            snackbar_theme=ft.SnackBarTheme(
                bgcolor=SURFACE_2,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
            dialog_theme=ft.DialogTheme(
                bgcolor=SURFACE,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
            switch_theme=ft.SwitchTheme(
                thumb_color=PAPER,
                track_color=SURFACE_2,
                track_outline_color=SURFACE_2,
                overlay_color=SURFACE_2,
            ),
            scrollbar_theme=ft.ScrollbarTheme(radius=0, thumb_color=SURFACE_2),
            splash_color=BG,
            highlight_color=BG,
        )
    except Exception:  # pragma: no cover - version differences
        pass


class App:
    """Widgets and behaviour. Constructed once per Flet session."""

    def __init__(self, page) -> None:
        import flet as ft

        self.ft = ft
        self.page = page
        self.state = State.load()

        self.picker = ft.FilePicker()
        try:
            page.services.append(self.picker)
        except Exception:  # pragma: no cover - older Flet
            page.overlay.append(self.picker)

        # Flat input: no outline, no radius. The tone step carries the affordance.
        self.path_field = ft.TextField(
            label="AppImage",
            hint_text="/home/you/Downloads/Some.App.AppImage",
            value="",
            expand=True,
            bgcolor=SURFACE_2,
            border_width=0,
            border_color=SURFACE_2,
            border_radius=0,
            color=PAPER,
            on_submit=self.preview,
        )
        self.name_field = ft.TextField(
            label="Name (optional)",
            value="",
            width=220,
            bgcolor=SURFACE_2,
            border_width=0,
            border_color=SURFACE_2,
            border_radius=0,
            color=PAPER,
        )
        self.extract_switch = ft.Switch(label="Unpack instead of keeping it", value=False)
        self.copy_switch = ft.Switch(label="Copy instead of moving", value=False)
        self.plan_box = ft.Column(spacing=4)
        self.apps_box = ft.Column(spacing=8)
        self.status = ft.Text("", size=12, color=MUTED)
        # Flat indeterminate bar: sharp corners, tone-step track, no accents.
        self.progress = ft.ProgressBar(
            visible=False,
            bar_height=6,
            color=PAPER,
            bgcolor=SURFACE_2,
            border_radius=0,
        )
        self.action_buttons: list = []

    # -- styles ------------------------------------------------------------

    def _button_style(self, primary: bool):
        """Sharp corners, solid fill, no outline."""
        ft = self.ft
        return ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=0),
            bgcolor=PAPER if primary else SURFACE_2,
            color=BG if primary else PAPER,
        )

    def _panel(self, controls, padding: int = 14):
        """A raised surface: tone step only, flat, square."""
        ft = self.ft
        return ft.Container(
            content=ft.Column(controls, spacing=6),
            padding=padding,
            bgcolor=SURFACE,
            border_radius=0,
        )

    def _thumbnail(self, data: bytes, size: int = 28):
        """An icon preview: base64-embedded, flat, square. Flet 1.0 takes a
        bare base64 string in `src` (the old src_base64 field is gone)."""
        ft = self.ft
        return ft.Image(
            src=base64.b64encode(data).decode("ascii"),
            width=size,
            height=size,
            fit=ft.BoxFit.CONTAIN,
        )

    # -- options -----------------------------------------------------------

    def options(self) -> InstallOptions:
        return InstallOptions(
            name=self.name_field.value or "",
            mode=MODE_EXTRACT if self.extract_switch.value else MODE_KEEP,
            copy=bool(self.copy_switch.value),
            timeout=600,
        )

    # -- view --------------------------------------------------------------

    def build(self) -> None:
        ft = self.ft
        logo = _logo_src()

        header_children = []
        if logo:
            header_children.append(ft.Image(src=logo, width=44, height=44))
        header_children.append(
            ft.Column(
                [
                    ft.Text("appimo", size=24, weight=ft.FontWeight.BOLD, color=PAPER),
                    ft.Text(
                        "Turn any AppImage into a real application in your start menu",
                        size=12,
                        color=MUTED,
                    ),
                ],
                spacing=0,
            )
        )

        # One root surface in the page background, so the whole window is the
        # base tone regardless of the host's default theme.
        preview_button = ft.Button(
            content=ft.Text("Preview"),
            icon=ft.Icons.SEARCH,
            style=self._button_style(primary=False),
            on_click=self.preview,
        )
        integrate_button = ft.FilledButton(
            content=ft.Text("Integrate"),
            icon=ft.Icons.ADD,
            style=self._button_style(primary=True),
            on_click=self.integrate,
        )
        self.action_buttons = [preview_button, integrate_button]

        body = [
            ft.Container(
                content=ft.Row(header_children, spacing=14),
                padding=ft.Padding.only(bottom=18),
            ),
            ft.Row(
                [
                    self.path_field,
                    ft.Button(
                        content=ft.Text("Browse"),
                        icon=ft.Icons.FOLDER_OPEN,
                        style=self._button_style(primary=False),
                        on_click=self.browse,
                    ),
                ],
                spacing=10,
            ),
            ft.Row(
                [self.name_field, self.extract_switch, self.copy_switch],
                spacing=20,
                wrap=True,
            ),
            ft.Row(
                [
                    preview_button,
                    integrate_button,
                ],
                spacing=10,
            ),
            self.progress,
            self._panel(
                [
                    ft.Text("What will change", weight=ft.FontWeight.BOLD, size=13, color=PAPER),
                    self.plan_box,
                ]
            ),
            ft.Text("Integrated applications", weight=ft.FontWeight.BOLD, size=13, color=PAPER),
            self.apps_box,
            self.status,
            ft.Text(f"appimo {__version__}", size=11, color=FAINT),
        ]

        # One root surface in the page background, so the whole window is the
        # base tone regardless of the host's default theme.
        try:
            root = ft.Column(body, spacing=20, expand=True, scroll=ft.ScrollMode.AUTO)
        except AttributeError:  # pragma: no cover - older Flet
            root = ft.Column(body, spacing=20, expand=True)

        self.page.add(ft.Container(content=root, expand=True, bgcolor=BG, padding=24))
        self.refresh()
        self._update()

    def _update(self) -> None:
        try:
            self.page.update()
        except Exception:  # pragma: no cover - session already closed
            pass

    def _notify(self, message: str, error: bool = False) -> None:
        self.status.value = message
        # Monochrome: emphasis comes from weight, not from a colour.
        self.status.color = PAPER
        self.status.weight = self.ft.FontWeight.BOLD if error else None
        self._update()
        if error:
            try:
                self.page.show_dialog(
                    self.ft.SnackBar(content=self.ft.Text(message, color=PAPER), bgcolor=SURFACE_2)
                )
            except Exception:  # pragma: no cover - version differences
                pass

    # -- actions -----------------------------------------------------------

    async def browse(self, _event) -> None:
        try:
            files = await self.picker.pick_files(
                dialog_title="Choose an AppImage",
                allow_multiple=False,
            )
        except Exception as exc:  # pragma: no cover - desktop only
            self._notify(f"file dialog unavailable: {exc}", error=True)
            return
        if files:
            chosen = getattr(files[0], "path", None) or str(files[0])
            self.path_field.value = chosen
            self.preview(None)

    def preview(self, _event) -> None:
        ft = self.ft
        raw = (self.path_field.value or "").strip()
        self.plan_box.controls.clear()

        if not raw:
            self.plan_box.controls.append(
                ft.Text("Choose an AppImage first.", size=12, color=MUTED)
            )
            self._update()
            return

        source = Path(raw).expanduser()
        try:
            plan = plan_install(source, self.options(), self.state)
        except AppimoError as exc:
            self.plan_box.controls.append(
                ft.Text(exc.message, size=12, color=PAPER, weight=ft.FontWeight.BOLD)
            )
            if exc.hint:
                self.plan_box.controls.append(ft.Text(exc.hint, size=11, color=MUTED))
            self._update()
            return

        for label, value in plan.summary():
            shown = _pretty(value) if "/" in str(value) else str(value)
            self.plan_box.controls.append(
                ft.Row(
                    [
                        ft.Text(label, size=12, color=MUTED, width=90),
                        ft.Text(shown, size=12, color=PAPER, selectable=True),
                    ]
                )
            )
        # A real look at the icon the bundle carries, before anything is
        # written. SVGs can't go through Image's base64 source; skip those.
        if plan.icon and "SVG" not in plan.icon.described:
            self.plan_box.controls.insert(
                0, ft.Row([self._thumbnail(plan.icon.data)], spacing=8)
            )
        for warning in plan.warnings:
            self.plan_box.controls.append(ft.Text(f"! {warning}", size=11, color=FAINT))
        self._update()

    # -- busy state ---------------------------------------------------------

    def _set_busy(self, busy: bool, message: str = "") -> None:
        """Show the progress bar and disable the action buttons while working."""
        self.progress.visible = busy
        for button in self.action_buttons:
            button.disabled = busy
        self.status.value = message
        self._update()

    def _do_integrate(self, raw: str):
        """The blocking half of integrate, run off the UI thread."""
        source = Path(raw).expanduser()
        options = self.options()
        try:
            plan = plan_install(source, options, self.state)
            record = apply_install(plan, options, self.state)
            return record, None
        except AppimoError as exc:
            return None, exc

    async def integrate(self, _event) -> None:
        raw = (self.path_field.value or "").strip()
        if not raw:
            self._notify("Choose an AppImage first.", error=True)
            return

        # unsquashfs can take seconds on a big bundle; keep the window
        # responsive and the bar animating by doing the work in a thread.
        self._set_busy(True, "Reading and integrating the bundle…")
        try:
            record, error = await asyncio.to_thread(self._do_integrate, raw)
        finally:
            self._set_busy(False)

        if error is not None:
            self._notify(error.message, error=True)
            return

        self.path_field.value = ""
        self.name_field.value = ""
        self.plan_box.controls.clear()
        self._notify(f'Launch "{record.name}" from your start menu')
        self.refresh()

    def remove(self, app_id: str) -> None:
        try:
            plan = plan_remove(app_id, state=self.state)
            name = plan.app.name
            apply_remove(plan, state=self.state)
        except AppimoError as exc:
            self._notify(exc.message, error=True)
            return
        self._notify(f'Removed "{name}"')
        self.refresh()

    def refresh(self) -> None:
        ft = self.ft
        self.apps_box.controls.clear()

        if not len(self.state):
            self.apps_box.controls.append(
                ft.Text("Nothing integrated yet.", size=12, color=FAINT)
            )
            return

        for app in self.state.all():
            mode = "unpacked" if app.mode == MODE_EXTRACT else "kept"
            # The installed hicolor icon, when we have one; a recessed square
            # placeholder keeps the rows aligned when we don't.
            lead: ft.Control
            icon_bytes = None
            for icon_file in app.icon_files:
                if icon_file.endswith(".png"):
                    try:
                        icon_bytes = Path(icon_file).read_bytes()
                    except OSError:  # pragma: no cover - vanished file
                        icon_bytes = None
                    break
            if icon_bytes:
                lead = self._thumbnail(icon_bytes, size=32)
            else:
                lead = ft.Container(width=32, height=32, bgcolor=SURFACE_2)
            self.apps_box.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            lead,
                            ft.Column(
                                [
                                    ft.Text(
                                        app.name,
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=PAPER,
                                    ),
                                    ft.Text(
                                        f"{mode} · {_pretty(app.managed_path)}",
                                        size=11,
                                        color=FAINT,
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                            ft.TextButton(
                                content=ft.Text("Remove", color=PAPER),
                                on_click=lambda _e, i=app.id: self.remove(i),
                            ),
                        ],
                        spacing=14,
                    ),
                    padding=10,
                    bgcolor=SURFACE,
                    border_radius=0,
                )
            )


def main(page) -> None:
    """Flet entry point."""
    import flet as ft

    page.title = "Appimo"
    _set_window(page, 780, 720)
    try:
        page.theme_mode = ft.ThemeMode.DARK
        # One surface edge to edge: the page background must match the root
        # container, or the content reads as a canvas inside another canvas.
        page.bgcolor = BG
    except Exception:  # pragma: no cover - version differences
        pass
    _apply_theme(page)
    App(page).build()


def run() -> int:
    """Start the GUI. Returns a process exit code."""
    try:
        import flet as ft
    except ImportError:  # pragma: no cover - optional dependency
        return 1
    root = assets_root()
    if root:
        ft.run(main, assets_dir=str(root))
    else:
        ft.run(main)
    return 0
