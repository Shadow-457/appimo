"""The command line interface, driven the way a user drives it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from appimo import paths
from appimo.cli import main


def test_no_command_prints_help(capsys) -> None:
    assert main([]) == 0
    assert "Turn any AppImage" in capsys.readouterr().out


def test_version_flag_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "appimo" in capsys.readouterr().out


def test_unknown_command_exits_two() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["frobnicate"])
    assert excinfo.value.code == 2


def test_info_describes_a_bundle_without_changing_anything(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["info", str(bundle)]) == 0
    out = capsys.readouterr().out
    assert "Demo App" in out
    assert "A demo application" in out
    assert "squashfs at byte" in out
    assert not paths.applications_dir().exists()
    assert bundle.exists()


def test_info_json_is_machine_readable(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["info", str(bundle), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "Demo App"
    assert payload["kind"] == "appimage"
    assert payload["icon"].endswith("demo.png")
    assert payload["categories"] == ["Utility", "Development"]


def test_install_then_list_then_remove(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["install", str(bundle)]) == 0
    out = capsys.readouterr().out
    assert "Launch" in out and "Demo App" in out
    assert "demo-app" in out

    assert main(["list"]) == 0
    assert "Demo App" in capsys.readouterr().out

    assert main(["remove", "Demo App"]) == 0
    assert "Removed" in capsys.readouterr().out

    assert main(["list"]) == 0
    assert "nothing integrated yet" in capsys.readouterr().out


def test_dry_run_changes_nothing(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["install", str(bundle), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert not paths.applications_dir().exists()
    assert not Path(paths.default_apps_dir()).exists()
    assert bundle.exists()


def test_install_json(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["install", str(bundle), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["results"][0]["id"] == "dev.appimo.demo-app"


def test_install_failure_sets_a_nonzero_exit_code(sandbox: Path, capsys) -> None:
    junk = sandbox / "Downloads" / "junk.bin"
    junk.write_bytes(b"definitely not an appimage")
    assert main(["install", str(junk)]) == 1
    err = capsys.readouterr().err
    assert "not an AppImage" in err


def test_install_failure_json_still_reports(sandbox: Path, capsys) -> None:
    junk = sandbox / "Downloads" / "junk.bin"
    junk.write_bytes(b"nope")
    assert main(["install", str(junk), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["results"][0]["ok"] is False


def test_multiple_paths_report_per_file(sandbox: Path, tmp_path: Path, capsys) -> None:
    from conftest import build_appdir, build_bundle

    one = build_bundle(build_appdir(tmp_path / "A", name="Alpha"), tmp_path / "Alpha.AppImage")
    two = build_bundle(build_appdir(tmp_path / "B", name="Beta"), tmp_path / "Beta.AppImage")
    junk = sandbox / "Downloads" / "junk.bin"
    junk.write_bytes(b"nope")

    assert main(["install", str(one), str(two), str(junk)]) == 1
    out = capsys.readouterr()
    assert "Alpha" in out.out and "Beta" in out.out
    assert "not an AppImage" in out.err

    # The two good bundles must still have been installed.
    assert main(["list", "--json"]) == 0
    ids = [a["id"] for a in json.loads(capsys.readouterr().out)["apps"]]
    assert ids == ["dev.appimo.alpha", "dev.appimo.beta"]


def test_alias_commands_work(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["integrate", str(bundle)]) == 0
    capsys.readouterr()
    assert main(["ls"]) == 0
    assert "Demo App" in capsys.readouterr().out
    assert main(["rm", "demo-app"]) == 0
    assert "Removed" in capsys.readouterr().out


def test_remove_unknown_target_fails(sandbox: Path, capsys) -> None:
    assert main(["remove", "ghost"]) == 1
    assert "nothing called" in capsys.readouterr().err


def test_remove_dry_run_keeps_everything(sandbox: Path, bundle: Path, capsys) -> None:
    main(["install", str(bundle)])
    capsys.readouterr()
    assert main(["remove", "demo-app", "--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out.lower()

    assert main(["list", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["apps"]) == 1


def test_doctor_runs_on_a_fresh_system(sandbox: Path, capsys) -> None:
    """A brand new home has no XDG directories yet. That is not a failure."""
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "unsquashfs" in out
    assert "FAIL" not in out


def test_doctor_inspects_a_bundle(sandbox: Path, bundle: Path, capsys) -> None:
    assert main(["doctor", str(bundle)]) == 0
    out = capsys.readouterr().out
    assert "squashfs payload" in out
    assert "found at byte" in out


def test_doctor_json(sandbox: Path, capsys) -> None:
    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert any(c["label"] == "unsquashfs" for c in payload["checks"])


def test_info_on_a_directory_appdir(sandbox: Path, appdir: Path, capsys) -> None:
    assert main(["info", str(appdir)]) == 0
    out = capsys.readouterr().out
    assert "appdir" in out
    assert "Demo App" in out


def test_menu_writes_a_launcher_with_an_icon(sandbox: Path, capsys) -> None:
    """`appimo menu` puts Appimo itself in the start menu."""
    assert main(["menu"]) == 0
    out = capsys.readouterr().out
    assert "start menu" in out

    entry = paths.applications_dir() / "dev.appimo.appimo.desktop"
    assert entry.exists()
    text = entry.read_text(encoding="utf-8")
    assert "Name=Appimo" in text
    assert "Exec=" in text and "gui" in text
    assert "X-Appimo-Managed=true" in text
    # The icon landed in the user's hicolor theme.
    assert (paths.hicolor_dir() / "256x256" / "apps" / "dev.appimo.appimo.png").exists()


def test_menu_twice_needs_force(sandbox: Path, capsys) -> None:
    assert main(["menu"]) == 0
    assert main(["menu"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["menu", "--force"]) == 0


def test_menu_remove(sandbox: Path, capsys) -> None:
    assert main(["menu"]) == 0
    assert main(["menu", "--remove"]) == 0
    assert not (
        paths.applications_dir() / "dev.appimo.appimo.desktop"
    ).exists()
    assert main(["menu", "--remove"]) == 0
    assert "was not installed" in capsys.readouterr().out
