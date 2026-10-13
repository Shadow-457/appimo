"""Desktop entry parsing and rendering."""

from __future__ import annotations

from pathlib import Path

from appimo.desktop import AppMetadata, DesktopEntry, render, validate

SAMPLE = """# a comment
[Desktop Entry]
Type=Application
Name=Boxes
Name[de]=Kisten
Comment=Run virtual machines
Exec=/usr/bin/boxes %U
Icon=org.gnome.Boxes
Categories=System;Utility;
MimeType=application/x-virt;
Terminal=false
StartupWMClass=boxes

[Desktop Action new]
Name=New
Exec=boxes --new
"""


def test_parse_reads_groups_keys_and_ignores_comments() -> None:
    entry = DesktopEntry.parse(SAMPLE)
    assert entry.get("Name") == "Boxes"
    assert entry.get("Type") == "Application"
    assert entry.has("StartupWMClass")
    assert "Desktop Action new" in entry.groups


def test_parse_is_tolerant_of_junk() -> None:
    entry = DesktopEntry.parse("garbage\n\nName=Fine\nno-equals-here\n")
    assert entry.get("Name") == "Fine"


def test_list_values_drop_trailing_empties() -> None:
    entry = DesktopEntry.parse(SAMPLE)
    assert entry.items("Categories") == ["System", "Utility"]
    assert entry.items("MimeType") == ["application/x-virt"]


def test_localised_lookup(monkeypatch) -> None:
    entry = DesktopEntry.parse(SAMPLE)
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    assert entry.getl("Name") == "Kisten"

    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert entry.getl("Name") == "Boxes"


def test_metadata_from_entry_keeps_field_codes() -> None:
    metadata = AppMetadata.from_entry(DesktopEntry.parse(SAMPLE), "org.gnome.Boxes")
    assert metadata.name == "Boxes"
    assert metadata.exec_arguments == ["%U"]
    assert metadata.icon_name == "org.gnome.Boxes"
    assert metadata.categories == ["System", "Utility"]
    assert metadata.terminal is False
    assert metadata.startup_wm_class == "boxes"


def test_render_produces_a_valid_launcher(tmp_path: Path) -> None:
    text = render(
        app_id="dev.appimo.boxes",
        name="Boxes",
        exec_value='"/home/me/Applications/Boxes.AppImage" %U',
        icon_name="dev.appimo.boxes",
        comment="Run virtual machines",
        categories=["System"],
        mime_types=["application/x-virt"],
        source="/home/me/Downloads/Boxes.AppImage",
        managed_path="/home/me/Applications/Boxes.AppImage",
    )
    assert "Exec=\"/home/me/Applications/Boxes.AppImage\" %U" in text
    assert "Categories=System;" in text
    assert "MimeType=application/x-virt;" in text
    assert "X-Appimo-Managed=true" in text
    assert "X-Appimo-Id=dev.appimo.boxes" in text
    assert text.endswith("\n")

    target = tmp_path / "dev.appimo.boxes.desktop"
    target.write_text(text, encoding="utf-8")
    assert [m for m in validate(target) if ": error" in m] == []


def test_render_never_copies_dangerous_keys() -> None:
    text = render(
        app_id="dev.appimo.x",
        name="X",
        exec_value="/x",
        icon_name="dev.appimo.x",
        extra={"Actions": "evil", "DBusActivatable": "true", "Keywords": "safe;"},
    )
    assert "Actions" not in text
    assert "DBusActivatable" not in text
    assert "Keywords=safe;" in text


def test_validate_returns_empty_for_a_clean_file(tmp_path: Path) -> None:
    target = tmp_path / "ok.desktop"
    target.write_text(
        "[Desktop Entry]\nType=Application\nName=Ok\nExec=/bin/true\n", encoding="utf-8"
    )
    assert [m for m in validate(target) if ": error" in m] == []
