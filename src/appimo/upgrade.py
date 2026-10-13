"""`appimo upgrade` — re-integrate an app when upstream publishes a new build.

AppImage projects move fast: builds get replaced in place at the same URL. The
record keeps the SHA-256 of the bundle at install time, so upgrading is a
three-way decision, never a blind re-download:

- the source is an https:// URL  -> re-download, hash it, install if changed
- the source is a local file that still exists
    - its hash matches the record   -> nothing to do
    - its hash differs              -> the file changed; offer to re-integrate
- the source is gone             -> say so; there is nothing to compare against

Install options that are easy to get wrong on a repeat (mode, name, id) are
re-used from the launcher and the state file, so an upgrade can never turn a
kept install into an unpacked one by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import fetch
from .errors import AppimoError
from .installer import MODE_EXTRACT, MODE_KEEP, InstallOptions, make_app_id
from .state import InstalledApp, State


@dataclass
class UpgradePlan:
    """What `upgrade` intends to do to one app, before doing it."""

    app: InstalledApp
    action: str  # "download+install" | "reinstall" | "current" | "unreachable"
    detail: str = ""
    #: The freshly downloaded bundle, when action involves one.
    staged: Path | None = None
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return self.detail or self.action


def _source_url(app: InstalledApp) -> str:
    """The recorded source, when it is an https URL."""
    source = app.source or ""
    return source if source.lower().startswith("https://") else ""


def plan_upgrade(key: str, *, state: State | None = None, refresh: bool = False) -> UpgradePlan:
    """Decide what upgrading `key` means, touching nothing."""
    state = state or State.load()
    app = state.find(key)

    if app.mode not in (MODE_KEEP, MODE_EXTRACT):  # pragma: no cover - defensive
        raise AppimoError(
            f"'{app.name}' has an unknown mode '{app.mode}'",
            hint="remove and install it again",
        )

    url = _source_url(app)
    if url:
        return UpgradePlan(app=app, action="download+install", detail=url)

    source = Path(app.source) if app.source else None
    if source is None or not source.exists():
        return UpgradePlan(
            app=app,
            action="unreachable",
            detail=f"the source file is gone ({app.source or 'never recorded'}); "
            "reinstall it manually to upgrade",
        )

    if not app.sha256:
        return UpgradePlan(
            app=app,
            action="reinstall",
            detail="installed before hash tracking; re-integrating from "
            f"{source}",
        )

    current = fetch.sha256_of(source)
    if current == app.sha256 and not refresh:
        return UpgradePlan(app=app, action="current", detail="already up to date")
    return UpgradePlan(
        app=app,
        action="reinstall",
        detail="the file changed since install; re-integrating"
        + (" (--refresh)" if refresh else ""),
    )


def apply_upgrade(
    plan: UpgradePlan,
    *,
    state: State | None = None,
    refresh: bool = False,
) -> InstalledApp | None:
    """Perform a plan. Returns the new record, or None when nothing changed."""
    from .installer import apply_install, plan_install  # local: import cycle

    state = state or State.load()
    app = plan.app

    if plan.action == "current":
        return None
    if plan.action == "unreachable":
        return None

    if plan.action == "download+install":
        url = _source_url(app)
        # Stage the download next to nothing else: a temp file Appimo deletes
        # (or installs) right after. The record's hash guards the transfer.
        staged = fetch.fetch(url, expected_sha256=app.sha256 if not refresh else "")
        source = staged
        cleanup = True
    else:
        source = Path(app.source)
        cleanup = False

    options = InstallOptions(
        app_id=app.id,
        name=app.name,
        # An unpacked install stays unpacked; a kept one stays kept.
        mode=app.mode if app.mode == MODE_EXTRACT else MODE_KEEP,
        force=True,
        refresh=refresh,
        with_icon=True,
    )
    try:
        fresh_plan = plan_install(source, options, state)
        # Carry the known upstream hash forward when the download could not
        # prove its own (a local file keeps whatever it is now).
        fresh_plan.source_sha256 = (
            fresh_plan.source_sha256
            if fresh_plan.source_sha256
            else fetch.sha256_of(source)
        )
        record = apply_install(fresh_plan, options, state)
    except AppimoError as exc:
        if plan.staged is not None:
            plan.staged.unlink(missing_ok=True)
        if "checksum" in exc.message and refresh:
            raise AppimoError(
                exc.message,
                hint="pass --refresh to accept upstream's new build anyway",
            ) from exc
        raise
    finally:
        if cleanup and plan.staged is not None:
            plan.staged.unlink(missing_ok=True)

    return record
