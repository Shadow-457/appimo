"""Installing and removing, end to end, against a sandboxed HOME."""

from __future__ import annotations

from pathlib import Path

import pytest

from appimo import paths
from appimo.errors import AlreadyInstalled, NotAnAppImage, NotInstalled
from appimo.installer import (
    MODE_EXTRACT,
    MODE_KEEP,
    InstallOptions,
    apply_install,
    apply_remove,
    plan_install,
    plan_remove,
)
from appimo.state import State

from conftest import build_appdir, build_bundle


def do_install(source: Path, state: State | None = None, **overrides):
    options = InstallOptions(**overrides)
    state = state or State.load()
    plan = plan_install(source, options, state)
    return plan, apply_install(plan, options, state)


# -- planning ---------------------------------------------------------------


def test_plan_writes_nothing(sandbox: Path, bundle: Path) -> None:
    plan = plan_install(bundle, InstallOptions(), State.load())
    assert plan.app_id == "dev.appimo.demo-app"
    assert plan.name == "Demo App"
    assert plan.mode == MODE_KEEP
    assert not paths.applications_dir().exists()
    assert not Path(plan.managed_path).exists()
    assert bundle.exists(), "planning must not move the source"


def test_plan_summary_is_complete(sandbox: Path, bundle: Path) -> None:
    plan = plan_install(bundle, InstallOptions(), State.load())
    labels = [label for label, _ in plan.summary()]
    assert labels == ["reading", "name", "id", "icon", "moved", "launcher"]


def test_missing_source_is_rejected_clearly(sandbox: Path) -> None:
    with pytest.raises(NotAnAppImage):
        plan_install(sandbox / "absent.AppImage", InstallOptions(), State.load())


# -- installing -------------------------------------------------------------


def test_install_creates_launcher_icon_and_moves_the_file(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle)

    assert Path(record.desktop_file).exists()
    assert Path(record.managed_path).exists()
    assert not bundle.exists(), "the source should have been moved, not left behind"
    assert record.mode == MODE_KEEP
    assert len(record.icon_files) == 1
    assert Path(record.icon_files[0]).exists()
    assert len(State.load()) == 1


def test_installed_file_keeps_its_content(sandbox: Path, bundle: Path) -> None:
    original = bundle.read_bytes()
    _, record = do_install(bundle)
    assert Path(record.managed_path).read_bytes() == original


def test_managed_file_is_executable(sandbox: Path, bundle: Path) -> None:
    import os

    _, record = do_install(bundle)
    assert os.access(record.managed_path, os.X_OK)


def test_exec_points_at_the_managed_file_and_is_quoted(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle)
    text = Path(record.desktop_file).read_text(encoding="utf-8")
    managed = record.managed_path
    assert f'Exec="{managed}" %U' in text
    assert "X-Appimo-Managed=true" in text
    assert "Icon=dev.appimo.demo-app" in text

    # No key that the desktop actually launches from may point back at the
    # download. (X-Appimo-Source intentionally records provenance.)
    launch_keys = {"Exec", "TryExec", "Path", "Icon"}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key in launch_keys:
            assert str(bundle) not in value, f"{key} still points at the download"


def test_icon_lands_in_the_right_hicolor_bucket(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle)
    icon = Path(record.icon_files[0])
    assert icon.parent == paths.hicolor_dir() / "256x256" / "apps"
    assert icon.name == "dev.appimo.demo-app.png"
    assert icon.read_bytes() == (bundle.parent / "AppDir" / "demo.png").read_bytes()


@pytest.mark.parametrize("location", ["root", ".DirIcon", "hicolor"])
def test_icon_is_found_wherever_an_appdir_puts_it(sandbox: Path, tmp_path: Path, location: str) -> None:
    appdir = build_appdir(tmp_path / f"AppDir-{location}", icon_location=location)
    source = build_bundle(appdir, tmp_path / f"Demo-{location}.AppImage")
    _, record = do_install(source)
    assert len(record.icon_files) == 1
    assert Path(record.icon_files[0]).exists()


def test_larger_raster_icon_wins_over_a_smaller_one(sandbox: Path, tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir", icon_size=256)
    (appdir / "usr/share/icons/hicolor/512x512/apps").mkdir(parents=True)
    from conftest import make_png

    (appdir / "usr/share/icons/hicolor/512x512/apps/demo.png").write_bytes(make_png(512, 512))
    source = build_bundle(appdir, tmp_path / "Demo.AppImage")

    plan = plan_install(source, InstallOptions(), State.load())
    assert plan.icon is not None
    assert "512x512" in str(plan.icon.path)


def test_install_without_an_icon_warns_but_succeeds(sandbox: Path, tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir", icon_location="none")
    source = build_bundle(appdir, tmp_path / "Demo.AppImage")
    plan, record = do_install(source)
    assert plan.icon is None
    assert any("no icon" in w for w in plan.warnings)
    assert record.icon_files == []
    assert Path(record.desktop_file).exists()


def test_copy_leaves_the_original_alone(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle, copy=True)
    assert bundle.exists(), "--copy must not move the source"
    assert Path(record.managed_path).exists()


def test_custom_name_and_id(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle, name="Renamed", app_id="org.example.custom")
    assert record.name == "Renamed"
    assert record.id == "org.example.custom"
    assert Path(record.desktop_file).name == "org.example.custom.desktop"


def test_hostile_name_cannot_escape_the_apps_directory(sandbox: Path, bundle: Path) -> None:
    plan = plan_install(bundle, InstallOptions(name="../../../../etc/passwd"), State.load())
    apps_dir = paths.default_apps_dir()
    assert plan.managed_path.parent == apps_dir
    assert apps_dir in plan.managed_path.resolve().parents


def test_duplicate_install_is_refused(sandbox: Path, tmp_path: Path) -> None:
    """A second bundle that resolves to the same launcher id must be refused."""
    first = build_bundle(build_appdir(tmp_path / "A"), tmp_path / "One.AppImage")
    do_install(first)

    second = build_bundle(build_appdir(tmp_path / "B"), tmp_path / "Two.AppImage")
    with pytest.raises(AlreadyInstalled) as excinfo:
        plan_install(second, InstallOptions(), State.load())
    assert "--force" in (excinfo.value.hint or "")


def test_rerunning_with_the_original_path_explains_the_move(sandbox: Path, bundle: Path) -> None:
    do_install(bundle)
    with pytest.raises(AlreadyInstalled) as excinfo:
        plan_install(bundle, InstallOptions(), State.load())
    assert "already integrated from this file" in excinfo.value.message
    assert "appimo remove" in (excinfo.value.hint or "")


def test_force_replaces_the_previous_integration(sandbox: Path, tmp_path: Path) -> None:
    first = build_bundle(build_appdir(tmp_path / "A"), tmp_path / "First.AppImage")
    _, record = do_install(first)

    second = build_bundle(build_appdir(tmp_path / "B"), tmp_path / "Second.AppImage")
    _, replacement = do_install(second, force=True)

    assert replacement.id == record.id
    assert len(State.load()) == 1
    assert Path(replacement.desktop_file).exists()


# -- extract mode -----------------------------------------------------------


def test_extract_mode_unpacks_and_launches_apprun(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle, mode=MODE_EXTRACT)
    assert record.mode == MODE_EXTRACT
    apprun = Path(record.managed_path) / "AppRun"
    assert apprun.exists()
    import os

    assert os.access(apprun, os.X_OK)
    text = Path(record.desktop_file).read_text(encoding="utf-8")
    assert f'Exec="{apprun}" %U' in text


@pytest.mark.parametrize("copy", [False, True])
def test_extract_mode_source_handling(sandbox: Path, bundle: Path, copy: bool) -> None:
    """Unpacking supersedes the AppImage: gone by default, kept with --copy."""
    plan, _ = do_install(bundle, mode=MODE_EXTRACT, copy=copy)
    assert plan.remove_source is (not copy)
    assert bundle.exists() is copy
    labels = [label for label, _ in plan.summary()]
    assert ("removed" in labels) is (not copy)


def test_extract_mode_from_an_appdir(sandbox: Path, tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir")
    _, record = do_install(appdir, mode=MODE_EXTRACT)
    apprun = Path(record.managed_path) / "AppRun"
    assert apprun.exists(), "an AppDir input should be copied, not require a squashfs offset"
    assert (Path(record.managed_path) / "demo.desktop").exists()


def test_extract_mode_requires_an_apprun(sandbox: Path, tmp_path: Path) -> None:
    appdir = build_appdir(tmp_path / "AppDir", app_run=False)
    source = build_bundle(appdir, tmp_path / "Demo.AppImage")
    from appimo.errors import UnreadableBundle

    with pytest.raises(UnreadableBundle):
        plan_install(source, InstallOptions(mode=MODE_EXTRACT), State.load())


# -- driver -----------------------------------------------------------------


def test_driver_removes_everything_it_created(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle)
    state = State.load()
    plan = plan_remove(record.name, state=state)
    apply_remove(plan, state=state)

    assert not Path(record.desktop_file).exists()
    assert not Path(record.managed_path).exists()
    for icon in record.icon_files:
        assert not Path(icon).exists()
    assert len(State.load()) == 0
    with pytest.raises(NotInstalled):
        plan_remove(record.name, state=State.load())


def test_driver_keep_files_leaves_the_application(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle)
    state = State.load()
    plan = plan_remove(record.id, keep_files=True, state=state)
    apply_remove(plan, keep_files=True, state=state)

    assert not Path(record.desktop_file).exists()
    assert Path(record.managed_path).exists()
    assert len(State.load()) == 0


def test_driver_is_idempotent_when_files_were_already_deleted(sandbox: Path, bundle: Path) -> None:
    _, record = do_install(bundle)
    Path(record.desktop_file).unlink()
    state = State.load()
    apply_remove(plan_remove(record.id, state=state), state=state)
    assert len(State.load()) == 0


def test_install_then_remove_twice_is_fine(sandbox: Path, tmp_path: Path) -> None:
    first = build_bundle(build_appdir(tmp_path / "A"), tmp_path / "One.AppImage")
    _, record = do_install(first)
    state = State.load()
    apply_remove(plan_remove(record.id, state=state), state=state)

    second = build_bundle(build_appdir(tmp_path / "B"), tmp_path / "Two.AppImage")
    _, again = do_install(second)
    assert again.id == record.id


# -- real bundles -----------------------------------------------------------


def test_against_a_real_appimage(sandbox: Path, real_appimage: Path) -> None:
    """Opt in with APPIMO_TEST_APPIMAGE=/path/to/real.AppImage."""
    import shutil

    local = sandbox / "Downloads" / real_appimage.name
    shutil.copy2(real_appimage, local)
    _, record = do_install(local)
    assert Path(record.desktop_file).exists()
    assert Path(record.managed_path).exists()
    assert len(State.load()) == 1
