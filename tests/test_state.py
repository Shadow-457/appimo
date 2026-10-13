"""The inventory store."""

from __future__ import annotations

from pathlib import Path

import pytest

from appimo.errors import AppimoError, NotInstalled
from appimo.state import InstalledApp, State


def make_app(app_id: str = "dev.appimo.demo-app", name: str = "Demo App") -> InstalledApp:
    return InstalledApp(
        id=app_id,
        name=name,
        desktop_file=f"/home/u/.local/share/applications/{app_id}.desktop",
        managed_path=f"/home/u/Applications/{name}.AppImage",
        mode="keep",
        source="/home/u/Downloads/Demo.AppImage",
    )


def test_round_trips_through_disk(sandbox: Path) -> None:
    state = State.load()
    state.add(make_app())
    state.save()

    reloaded = State.load()
    assert len(reloaded) == 1
    assert reloaded.find("dev.appimo.demo-app").name == "Demo App"


def test_load_missing_file_is_empty(sandbox: Path) -> None:
    assert len(State.load()) == 0


def test_find_matches_id_name_and_slug(sandbox: Path) -> None:
    state = State.load()
    state.add(make_app())
    for key in ("dev.appimo.demo-app", "Demo App", "demo app", "demo-app", "DEMO-APP"):
        assert state.find(key).id == "dev.appimo.demo-app"


def test_find_unknown_raises_with_a_hint(sandbox: Path) -> None:
    with pytest.raises(NotInstalled) as excinfo:
        State.load().find("nope")
    assert "appimo list" in (excinfo.value.hint or "")


def test_all_is_sorted_by_id(sandbox: Path) -> None:
    state = State.load()
    state.add(make_app("dev.appimo.zulu", "Zulu"))
    state.add(make_app("dev.appimo.alpha", "Alpha"))
    assert [a.id for a in state.all()] == ["dev.appimo.alpha", "dev.appimo.zulu"]


def test_corrupt_inventory_raises_a_readable_error(sandbox: Path) -> None:
    from appimo import paths

    path = paths.state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(AppimoError) as excinfo:
        State.load()
    assert "could not be read" in excinfo.value.message
    assert ".bak" in (excinfo.value.hint or "")


def test_unknown_keys_are_tolerated(sandbox: Path) -> None:
    """A newer Appimo may write fields this one does not know about."""
    app = InstalledApp.from_dict({"id": "x", "name": "X", "future_field": 1})
    assert app.id == "x"


def test_save_is_atomic_and_leaves_no_temp_file(sandbox: Path) -> None:
    state = State.load()
    state.add(make_app())
    state.save()
    from appimo import paths

    assert paths.state_file().exists()
    assert not paths.state_file().with_suffix(".json.tmp").exists()
