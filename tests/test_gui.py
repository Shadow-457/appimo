"""The graphical interface.

Flet is an optional dependency, so these tests skip when it is absent. The
widget tree is built against a stub page, which exercises the real widget
code paths without needing a display server.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

ft = pytest.importorskip("flet", reason="flet is an optional dependency")

from appimo.cli import main  # noqa: E402
from appimo.gui.app import App, assets_root  # noqa: E402


class StubPage:
    """Just enough of `ft.Page` to build and drive the widget tree headlessly."""

    def __init__(self) -> None:
        self.services: list = []
        self.overlay: list = []
        self.controls: list = []
        self.dialogs: list = []
        self.title = ""

    def add(self, *controls) -> None:
        self.controls.extend(controls)

    def update(self) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)


@pytest.fixture
def gui(sandbox: Path):
    page = StubPage()
    app = App(page)
    app.build()
    return app, page


def test_control_tree_builds(gui) -> None:
    app, page = gui
    # Everything lives inside one flat root surface, which carries the base
    # tone so the window never inherits the host's default theme.
    assert len(page.controls) == 1
    root = page.controls[0]
    assert root.bgcolor == "#1A1815"
    assert root.border_radius in (None, 0)
    assert len(root.content.controls) >= 8
    assert page.services, "the file picker must be registered as a service"


def test_preview_lists_the_plan_and_writes_nothing(gui, bundle: Path) -> None:
    app, _page = gui
    app.path_field.value = str(bundle)

    app.preview(None)

    labels = [row.controls[0].value for row in app.plan_box.controls if hasattr(row, "controls")]
    assert labels == ["reading", "name", "id", "icon", "moved", "launcher"]
    assert bundle.exists(), "preview must not move the file"
    assert not app.state.apps


def test_preview_explains_a_bad_path(gui, sandbox: Path) -> None:
    app, _page = gui
    app.path_field.value = str(sandbox / "Downloads" / "missing.AppImage")
    app.preview(None)
    assert "no such file" in app.plan_box.controls[0].value


def test_preview_with_empty_input_prompts(gui) -> None:
    app, _page = gui
    app.path_field.value = ""
    app.preview(None)
    assert "Choose an AppImage" in app.plan_box.controls[0].value


def test_integrate_then_remove(gui, bundle: Path) -> None:
    app, _page = gui
    app.path_field.value = str(bundle)

    asyncio.run(app.integrate(None))
    assert "Launch" in app.status.value
    assert app.path_field.value == "", "the field should be cleared after a successful install"
    assert len(app.state.apps) == 1
    assert len(app.apps_box.controls) == 1

    app.remove("dev.appimo.demo-app")
    assert "Removed" in app.status.value
    assert not app.state.apps


def test_integrate_without_a_path_warns(gui) -> None:
    app, page = gui
    app.path_field.value = ""
    asyncio.run(app.integrate(None))
    assert "Choose an AppImage" in app.status.value
    assert page.dialogs, "errors should surface as a snackbar"


def test_double_integrate_reports_the_conflict(gui, bundle: Path) -> None:
    app, _page = gui
    app.path_field.value = str(bundle)
    asyncio.run(app.integrate(None))

    app.path_field.value = str(bundle)
    asyncio.run(app.integrate(None))
    assert "already integrated" in app.status.value


def test_empty_state_is_explained(gui) -> None:
    app, _page = gui
    assert len(app.apps_box.controls) == 1
    assert "Nothing integrated yet" in app.apps_box.controls[0].value


def test_extract_switch_selects_extract_mode(gui) -> None:
    from appimo.installer import MODE_EXTRACT, MODE_KEEP

    app, _page = gui
    assert app.options().mode == MODE_KEEP
    app.extract_switch.value = True
    assert app.options().mode == MODE_EXTRACT


def test_logo_is_served_from_the_assets_directory() -> None:
    root = assets_root()
    if root is None:
        pytest.skip("not running from a checkout with assets/")
    from appimo.gui.app import LOGO_RELATIVE

    assert (root / LOGO_RELATIVE).exists()
    assert not Path(LOGO_RELATIVE).is_absolute(), "Flet cannot serve an absolute path"


def test_gui_command_reports_a_missing_flet(monkeypatch, capsys) -> None:
    """`appimo gui` without Flet should explain itself, not traceback.

    Setting the package to None in sys.modules makes the relative import raise
    ImportError, which is exactly what happens when Flet is not installed.
    Crucially this never reaches `ft.run()`, which would block forever.
    """
    import sys

    # `appimo.gui.app` is already imported by this module, so clearing it is
    # required: otherwise the relative import is served straight from the
    # module cache and the GUI would really launch (and hang the suite).
    monkeypatch.setitem(sys.modules, "appimo.gui", None)
    monkeypatch.delitem(sys.modules, "appimo.gui.app", raising=False)
    assert main(["gui"]) == 1
    assert "Flet" in capsys.readouterr().err
