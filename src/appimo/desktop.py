"""Desktop entry parsing, rendering and validation.

The Desktop Entry Specification is a small INI dialect with its own rules
(localised keys, semicolon-terminated lists, its own `Exec` quoting). We parse
tolerantly — real-world AppImages contain hand-written files — but we render
strictly and hand the result to `desktop-file-validate` when it's available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .util import collapse_whitespace, split_exec

MAIN_GROUP = "Desktop Entry"

#: Keys we rewrite rather than copy: they must point at the managed file.
REWRITTEN_KEYS = frozenset({"Exec", "TryExec", "Icon", "Path"})

#: Keys we never copy from an untrusted bundle into a user-visible launcher.
DROPPED_KEYS = frozenset(
    {"Actions", "DBusActivatable", "X-GNOME-Autostart-enabled", "X-KDE-autostart-after"}
)


@dataclass
class DesktopEntry:
    """A parsed desktop file, preserving group and key order."""

    groups: dict[str, "dict[str, str]"] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> "DesktopEntry":
        entry = cls()
        group = MAIN_GROUP
        entry.groups[group] = {}
        for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip().lstrip("\ufeff")
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                group = line[1:-1]
                entry.groups.setdefault(group, {})
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            entry.groups[group][key.strip()] = value.strip()
        return entry

    @classmethod
    def read(cls, path: Path) -> "DesktopEntry":
        return cls.parse(path.read_text(encoding="utf-8", errors="replace"))

    # -- accessors ---------------------------------------------------------

    def get(self, key: str, default: str = "") -> str:
        return self.groups.get(MAIN_GROUP, {}).get(key, default)

    def getl(self, key: str, default: str = "") -> str:
        """`get`, but prefers a key localised to the user's locale."""
        values = self.groups.get(MAIN_GROUP, {})
        for suffix in _locale_suffixes():
            match = values.get(f"{key}[{suffix}]")
            if match:
                return match
        return values.get(key, default)

    def items(self, key: str) -> list[str]:
        """A semicolon-terminated list value, e.g. `Categories`."""
        return [item for item in self.get(key).split(";") if item.strip()]

    def has(self, key: str) -> bool:
        return key in self.groups.get(MAIN_GROUP, {})


def _locale_suffixes() -> list[str]:
    """Locale keys to try, most specific first: `de_DE.UTF-8` -> `de_DE`, `de`."""
    raw = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    )
    code = raw.split(".")[0].split("@")[0]
    if not code or code in {"C", "POSIX"}:
        return []
    suffixes = [code]
    if "_" in code:
        suffixes.append(code.split("_")[0])
    return suffixes


@dataclass
class AppMetadata:
    """The subset of a bundle's desktop file Appimo actually uses."""

    name: str
    comment: str = ""
    icon_name: str = ""
    categories: list[str] = field(default_factory=list)
    mime_types: list[str] = field(default_factory=list)
    terminal: bool = False
    startup_wm_class: str = ""
    #: Trailing arguments from the source `Exec`, field codes included.
    exec_arguments: list[str] = field(default_factory=list)
    #: The bundle's own desktop file id, e.g. `org.gnome.Boxes`.
    source_id: str = ""
    #: Extra keys worth carrying over unchanged.
    passthrough: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_entry(cls, entry: DesktopEntry, source_id: str = "") -> "AppMetadata":
        _command, arguments = split_exec(entry.get("Exec"))
        passthrough = {}
        for key in ("StartupNotify", "GenericName", "Keywords", "NoDisplay"):
            if entry.has(key) and entry.get(key):
                passthrough[key] = entry.get(key)

        return cls(
            name=collapse_whitespace(entry.getl("Name")) or source_id,
            comment=collapse_whitespace(entry.getl("Comment")),
            icon_name=entry.get("Icon", "").strip(),
            categories=entry.items("Categories"),
            mime_types=entry.items("MimeType"),
            terminal=entry.get("Terminal").strip().lower() == "true",
            startup_wm_class=entry.get("StartupWMClass", "").strip(),
            exec_arguments=arguments,
            source_id=source_id,
            passthrough=passthrough,
        )


def render(
    *,
    app_id: str,
    name: str,
    exec_value: str,
    icon_name: str,
    comment: str = "",
    categories: list[str] | None = None,
    mime_types: list[str] | None = None,
    terminal: bool = False,
    startup_wm_class: str = "",
    source: str = "",
    managed_path: str = "",
    extra: dict[str, str] | None = None,
) -> str:
    """Render the launcher Appimo installs.

    Everything written here is deliberate: the id is namespaced, `Exec` points
    at the managed file rather than the download, and the `X-Appimo-*` keys
    make the entry self-identifying even if the state file is lost.
    """
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.1",
        f"Name={name}",
    ]
    if comment:
        lines.append(f"Comment={comment}")
    lines.append(f"Exec={exec_value}")
    if icon_name:
        lines.append(f"Icon={icon_name}")
    lines.append(f"Terminal={'true' if terminal else 'false'}")
    if categories:
        joined = "".join(f"{c};" for c in categories)
        lines.append(f"Categories={joined}")
    if mime_types:
        joined = "".join(f"{m};" for m in mime_types)
        lines.append(f"MimeType={joined}")
    if startup_wm_class:
        lines.append(f"StartupWMClass={startup_wm_class}")
    for key, value in (extra or {}).items():
        if key not in REWRITTEN_KEYS and key not in DROPPED_KEYS:
            lines.append(f"{key}={value}")
    lines.append("X-Appimo-Managed=true")
    lines.append(f"X-Appimo-Id={app_id}")
    if source:
        lines.append(f"X-Appimo-Source={source}")
    if managed_path:
        lines.append(f"X-Appimo-Path={managed_path}")
    lines.append("")
    return "\n".join(lines)


def validate(path: Path) -> list[str]:
    """Run `desktop-file-validate`; returns its messages (empty when clean)."""
    tool = shutil.which("desktop-file-validate")
    if not tool:
        return []
    try:
        result = subprocess.run(
            [tool, str(path)], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):  # pragma: no cover - environment
        return []
    output = f"{result.stdout}\n{result.stderr}".strip()
    return [line.strip() for line in output.splitlines() if line.strip()]


def refresh_databases(app_dir: Path, *, mime_types: bool) -> list[str]:
    """Conditionally refresh desktop caches. Returns notes for the caller.

    Most desktops pick up a new launcher on their own, so this is deliberately
    conservative: `update-desktop-database` only matters when the entry claims
    MIME types, and `gtk-update-icon-cache` only does anything for a directory
    that actually holds an `index.theme`.
    """
    notes: list[str] = []
    if mime_types and (tool := shutil.which("update-desktop-database")):
        try:
            subprocess.run([tool, str(app_dir)], capture_output=True, timeout=30)
            notes.append("refreshed the MIME database")
        except (OSError, subprocess.TimeoutExpired):  # pragma: no cover
            pass
    return notes
