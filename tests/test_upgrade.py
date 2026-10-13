"""`appimo upgrade`: hash-tracked re-integration, never a blind re-download."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from appimo import paths
from appimo.cli import main
from appimo.fetch import sha256_of
from appimo.state import InstalledApp, State


def _record(bundle: Path, *, sha: str = "", source: str = "") -> InstalledApp:
    return InstalledApp(
        id="dev.appimo.demo-app",
        name="Demo App",
        desktop_file=str(paths.applications_dir() / "dev.appimo.demo-app.desktop"),
        managed_path=str(paths.default_apps_dir() / "Demo App.AppImage"),
        mode="keep",
        source=source or str(bundle),
        sha256=sha or sha256_of(bundle),
    )


def test_upgrade_reports_current_when_nothing_changed(sandbox: Path, bundle: Path, capsys) -> None:
    state = State()
    state.add(_record(bundle))
    state.save()

    assert main(["upgrade", "Demo App"]) == 0
    out = capsys.readouterr().out
    assert "already up to date" in out
    assert bundle.exists()  # untouched


def test_upgrade_reintegrates_when_the_local_file_changed(sandbox: Path, bundle: Path, capsys) -> None:
    state = State()
    state.add(_record(bundle, sha="0" * 64))  # deliberately stale
    state.save()
    expected = sha256_of(bundle)

    assert main(["upgrade", "demo-app"]) == 0
    out = capsys.readouterr().out
    assert "upgraded" in out
    # The refreshed record carries the file's real hash now.
    record = State.load().find("demo-app")
    assert record.sha256 == expected
    assert record.installed_at  # re-applied, not just rewritten


def test_upgrade_says_so_when_the_source_is_gone(sandbox: Path, bundle: Path, capsys) -> None:
    state = State()
    state.add(_record(bundle, source="/nonexistent/Demo.AppImage"))
    state.save()

    assert main(["upgrade"]) == 0
    assert "source file is gone" in capsys.readouterr().out


def test_upgrade_without_hash_still_reinstalls(sandbox: Path, bundle: Path, capsys) -> None:
    """Installs from before hash tracking existed upgrade by full re-check."""
    state = State()
    record = _record(bundle, sha="")
    record.sha256 = ""
    state.add(record)
    state.save()
    expected = sha256_of(bundle)

    assert main(["upgrade", "Demo App"]) == 0
    out = capsys.readouterr().out
    assert "hash tracking" in out
    assert State.load().find("demo-app").sha256 == expected


def test_upgrade_dry_run_touches_nothing(sandbox: Path, bundle: Path, capsys) -> None:
    state = State()
    state.add(_record(bundle, sha="0" * 64))
    state.save()

    assert main(["upgrade", "--dry-run", "Demo App"]) == 0
    assert "dry run" in capsys.readouterr().out
    assert State.load().find("demo-app").sha256 == "0" * 64


def test_upgrade_with_no_integrations(sandbox: Path, capsys) -> None:
    assert main(["upgrade"]) == 0
    assert "nothing integrated" in capsys.readouterr().out


def test_install_records_the_source_hash(sandbox: Path, bundle: Path, capsys) -> None:
    expected = sha256_of(bundle)  # install moves the file; hash it first
    assert main(["install", str(bundle)]) == 0
    record = State.load().find("demo-app")
    assert record.sha256 == expected


def test_install_from_url_records_the_url(sandbox: Path, bundle: Path, monkeypatch, capsys) -> None:
    """An https:// source installs via download and is remembered as a URL."""
    from appimo import fetch

    payload = bundle.read_bytes()

    class FakeResponse:
        headers = {"Content-Length": str(len(payload))}
        _done = False
        def read(self, n=-1):
            if self._done:
                return b""
            self._done = True
            return payload
        def close(self):
            pass
    def fake_open(url):
        assert url.startswith("https://")
        return FakeResponse()

    monkeypatch.setattr(fetch, "_open", fake_open)

    assert main(["install", "https://example.com/Demo.AppImage"]) == 0
    record = State.load().find("demo-app")
    assert record.source == "https://example.com/Demo.AppImage"
    assert record.sha256 == hashlib.sha256(payload).hexdigest()
