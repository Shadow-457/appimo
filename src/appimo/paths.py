"""Where everything lives.

Appimo is a per-user tool by design: every path here is inside the invoking
user's home directory. Nothing in this module ever returns a system-wide
location, because writing to /usr is what breaks immutable distros.
"""

from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    """The invoking user's home directory."""
    env = os.environ.get("HOME")
    return Path(env) if env else Path.home()


def xdg_data_home() -> Path:
    """`$XDG_DATA_HOME`, defaulting to `~/.local/share` per the basedir spec."""
    env = os.environ.get("XDG_DATA_HOME")
    return Path(env) if env else home() / ".local" / "share"


def applications_dir() -> Path:
    """Where .desktop launchers go. User entries here win over /usr/share."""
    return xdg_data_home() / "applications"


def hicolor_dir() -> Path:
    """The user's hicolor icon theme root."""
    return xdg_data_home() / "icons" / "hicolor"


def appimo_dir() -> Path:
    """Appimo's own state directory."""
    return xdg_data_home() / "appimo"


def state_file() -> Path:
    """JSON inventory of everything Appimo has integrated."""
    return appimo_dir() / "state.json"


def default_apps_dir() -> Path:
    """Where managed AppImages are kept.

    `~/Applications` rather than a hidden directory, so the files stay findable
    and the user can see what they have. Overridable with `--dir` or
    `$APPIMO_APPS_DIR`.
    """
    env = os.environ.get("APPIMO_APPS_DIR")
    return Path(env) if env else home() / "Applications"
