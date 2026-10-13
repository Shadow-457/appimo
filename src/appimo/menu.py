"""Appimo's own start-menu entry.

`appimo install` integrates other applications, but nothing ever introduced
Appimo itself to the start menu — so after installing, the GUI was reachable
only by typing `appimo gui` into a terminal. `appimo menu` writes a launcher
for the GUI the same way Appimo writes launchers for the applications it
manages: a namespaced desktop entry in `~/.local/share/applications` and an
icon in the user's hicolor theme. The installer runs it automatically; it is
also a command, so it can be re-run or undone.

The entry is deliberately *not* recorded in the state file: it is not an
integrated application, and `appimo remove` is about AppImages.
"""

from __future__ import annotations

import shutil
import sys
from importlib import resources
from pathlib import Path

from . import desktop, paths
from .errors import AppimoError
from .installer import icon_destination
from .util import build_exec

#: Appimo's own launcher id. Namespaced like every other entry we write, so
#: it can never shadow a distro package's launcher.
APP_ID = "dev.appimo.appimo"

DISPLAY_NAME = "Appimo"
COMMENT = "Turn any AppImage into a real application in your start menu."
CATEGORIES = ["Utility", "Development"]

#: The icon bundled into the wheel (`force-include` in pyproject.toml) and,
#: in a checkout, read straight from `assets/`.
ICON_RESOURCE = "_icons/appimo-icon-256.png"
ICON_ASSET = "logo/appimo-icon-256.png"


def _find_command() -> Path:
    """The `appimo` executable the launcher should point at."""
    found = shutil.which("appimo")
    if found:
        return Path(found)
    # Fallback for the odd shell that has the venv bin dir off PATH but the
    # script itself running: sys.argv[0] is the entry point being executed.
    candidate = Path(sys.argv[0]).resolve()
    if candidate.name == "appimo" and candidate.exists():
        return candidate
    raise AppimoError(
        "could not find the appimo command on PATH",
        hint="open a new shell (uv/pipx add ~/.local/bin), then run 'appimo menu'",
    )


def _icon_bytes() -> bytes | None:
    """Appimo's 256px icon, from the checkout's assets or the wheel."""
    try:  # a source checkout has the full assets tree
        from .gui.app import assets_root

        root = assets_root()
        if root:
            candidate = root / ICON_ASSET
            if candidate.exists():
                return candidate.read_bytes()
    except Exception:  # noqa: BLE001 - the GUI must never break the CLI here
        pass
    try:  # an installed wheel carries a copy inside the package
        resource = resources.files("appimo").joinpath(ICON_RESOURCE)
        if resource.is_file():
            return resource.read_bytes()
    except (ModuleNotFoundError, FileNotFoundError, OSError):
        pass
    return None


def install_own_launcher(*, force: bool = False) -> tuple[Path, list[str]]:
    """Write Appimo's desktop entry (and icon). Returns its path + notes."""
    command = _find_command()
    warnings: list[str] = []

    icon_path = icon_destination(APP_ID, "png", 256)
    data = _icon_bytes()
    if data:
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        icon_path.write_bytes(data)
    else:
        warnings.append("the Appimo icon was not found; the theme default is used")

    desktop_path = paths.applications_dir() / f"{APP_ID}{desktop_id_suffix()}"
    if desktop_path.exists() and not force:
        raise AppimoError(
            f"Appimo's launcher already exists ({desktop_path})",
            hint="use --force to refresh it, or --remove to delete it",
        )

    contents = desktop.render(
        app_id=APP_ID,
        name=DISPLAY_NAME,
        exec_value=build_exec(str(command), ["gui"]),
        icon_name=APP_ID if data else "application-x-executable",
        comment=COMMENT,
        categories=CATEGORIES,
        terminal=False,
        startup_wm_class=APP_ID,
        source="self",
    )
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    desktop_path.write_text(contents, encoding="utf-8")

    messages = desktop.validate(desktop_path)
    errors = [m for m in messages if ": error" in m or ":error" in m]
    if errors:
        desktop_path.unlink(missing_ok=True)
        raise AppimoError("the generated launcher failed validation", hint=errors[0])

    return desktop_path, warnings


def remove_own_launcher() -> bool:
    """Remove Appimo's own entry. Returns whether anything was there."""
    removed = False
    for path in (
        paths.applications_dir() / f"{APP_ID}{desktop_id_suffix()}",
        icon_destination(APP_ID, "png", 256),
    ):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def desktop_id_suffix() -> str:
    """`.desktop`, kept in one place next to the installer's constant."""
    from .installer import ID_SUFFIX

    return ID_SUFFIX
