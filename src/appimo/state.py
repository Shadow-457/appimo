"""The inventory of what Appimo has integrated.

Kept as plain JSON in `~/.local/share/appimo/state.json` so it is inspectable,
diffable and hand-editable. The desktop files also carry `X-Appimo-*` keys, so
`appimo list` can still identify its own launchers if this file is lost.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .errors import AppimoError, NotInstalled
from .util import slugify


@dataclass
class InstalledApp:
    """One integrated application.

    Every field has a default on purpose. A state file written by a different
    Appimo version should still load, so a record never silently disappears and
    leaves an integrated app that can no longer be managed.
    """

    id: str = ""
    name: str = ""
    desktop_file: str = ""
    managed_path: str = ""
    mode: str = "keep"  # "keep" or "extract"
    source: str = ""
    #: SHA-256 of the source bundle at install time. `appimo upgrade` compares
    #: against it to decide whether upstream has published something new.
    sha256: str = ""
    icon_files: list[str] = field(default_factory=list)
    version: str = ""
    installed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "InstalledApp":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class State:
    """Load, mutate and persist the inventory."""

    def __init__(self, path: Path | None = None, apps: dict[str, InstalledApp] | None = None) -> None:
        self.path = path or paths.state_file()
        self.apps: dict[str, InstalledApp] = apps or {}

    # -- persistence -------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> "State":
        target = path or paths.state_file()
        if not target.exists():
            return cls(target)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise AppimoError(
                f"the inventory at {target} could not be read ({exc.__class__.__name__})",
                hint=f"move it aside and run 'appimo list' again: mv {target} {target}.bak",
            ) from exc
        apps = {}
        for record in payload.get("apps", []):
            try:
                app = InstalledApp.from_dict(record)
            except (TypeError, AttributeError):
                continue
            if not app.id:
                continue  # unusable: nothing to look it up by
            apps[app.id] = app
        return cls(target, apps)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "apps": [self.apps[key].to_dict() for key in sorted(self.apps)],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    # -- queries -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.apps)

    def all(self) -> list[InstalledApp]:
        return [self.apps[key] for key in sorted(self.apps)]

    def find(self, key: str) -> InstalledApp:
        """Look an app up by id, name, or slug of either."""
        if key in self.apps:
            return self.apps[key]
        wanted = slugify(key)
        for app in self.apps.values():
            if slugify(app.name) == wanted or slugify(app.id) == wanted:
                return app
        raise NotInstalled(
            f"nothing called '{key}' is integrated",
            hint="run 'appimo list' to see what is",
        )

    def has(self, app_id: str) -> bool:
        return app_id in self.apps

    # -- mutation ----------------------------------------------------------

    def add(self, app: InstalledApp) -> None:
        self.apps[app.id] = app

    def remove(self, app_id: str) -> InstalledApp:
        return self.apps.pop(app_id)
