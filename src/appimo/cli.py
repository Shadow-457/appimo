"""The `appimo` command line interface.

Output is deliberately plain and aligned: it is meant to be readable when
pasted into a bug report, and to look good in a screenshot.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import __version__, doctor, installer, menu, paths
from .appimage import inspect
from .errors import AppimoError, NotInstalled
from .installer import (
    MODE_EXTRACT,
    MODE_KEEP,
    InstallOptions,
    apply_install,
    apply_remove,
    plan_install,
    plan_remove,
)
from .state import State

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

_CODES = {
    "reset": "\x1b[0m",
    "dim": "\x1b[2m",
    "bold": "\x1b[1m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "cyan": "\x1b[36m",
}

_STATUS_COLOUR = {
    doctor.OK: "green",
    doctor.WARN: "yellow",
    doctor.FAIL: "red",
    doctor.INFO: "dim",
}

LABEL_WIDTH = 10


class Out:
    """Aligned, colour-aware output that degrades to plain text when piped."""

    def __init__(self, stream=None) -> None:
        self.stream = stream or sys.stdout
        self.colour = self.stream.isatty() and not os.environ.get("NO_COLOR")
        self.unicode = self._supports("✓")

    def _supports(self, text: str) -> bool:
        encoding = getattr(self.stream, "encoding", None) or "utf-8"
        try:
            text.encode(encoding)
            return True
        except (UnicodeEncodeError, LookupError):
            return False

    def paint(self, text: str, *styles: str) -> str:
        if not self.colour:
            return text
        return "".join(_CODES[s] for s in styles) + text + _CODES["reset"]

    def row(self, label: str, value: Any, *, width: int = LABEL_WIDTH) -> None:
        padded = label.ljust(max(width, len(label) + 1))
        print(f"  {self.paint(padded, 'dim')}{value}", file=self.stream)

    def blank(self) -> None:
        print("", file=self.stream)

    def done(self, message: str) -> None:
        mark = self.paint("✓", "green") if self.unicode else self.paint("ok", "green")
        print(f"  {mark} {message}", file=self.stream)

    def warn(self, message: str) -> None:
        mark = "!" if not self.unicode else "!"
        print(f"  {self.paint(mark, 'yellow')} {message}", file=self.stream)

    def note(self, message: str) -> None:
        print(f"  {self.paint(message, 'dim')}", file=self.stream)

    def heading(self, message: str) -> None:
        print(self.paint(message, "bold"), file=self.stream)

    def error(self, message: str, hint: str | None = None) -> None:
        stream = sys.stderr
        print(f"appimo: {self.paint(message, 'red')}", file=stream)
        if hint:
            print(f"        {self.paint(hint, 'dim')}", file=stream)


def pretty_path(path: str | Path) -> str:
    """Abbreviate the home directory to `~` for readable output."""
    text = str(path)
    home = str(paths.home())
    return "~" + text[len(home) :] if text.startswith(home) else text


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_install(args: argparse.Namespace, out: Out) -> int:
    options = InstallOptions(
        app_id=args.id or "",
        name=args.name or "",
        apps_dir=Path(args.dir).expanduser() if args.dir else None,
        mode=MODE_EXTRACT if args.extract else MODE_KEEP,
        copy=args.copy,
        force=args.force,
        with_icon=not args.no_icon,
        unsafe_extract=args.unsafe_extract,
        timeout=args.timeout,
    )
    state = State.load()
    results: list[dict[str, Any]] = []
    failures = 0

    for raw in args.paths:
        source = Path(raw).expanduser()
        try:
            plan = plan_install(source, options, state)
        except AppimoError as exc:
            failures += 1
            if args.json:
                results.append({"source": str(source), "ok": False, "error": exc.message})
            else:
                out.blank()
                out.error(exc.message, exc.hint)
            continue

        if args.dry_run:
            if args.json:
                results.append(
                    {
                        "source": str(source),
                        "ok": True,
                        "dry_run": True,
                        "id": plan.app_id,
                        "name": plan.name,
                        "managed_path": str(plan.managed_path),
                        "desktop_file": str(plan.desktop_path),
                        "exec": plan.exec_value,
                        "icon": str(plan.icon.path) if plan.icon else None,
                    }
                )
            else:
                out.blank()
                for label, value in plan.summary():
                    out.row(label, pretty_path(value) if "/" in str(value) else value)
                out.note("dry run — nothing was written")
                for warning in plan.warnings:
                    out.warn(warning)
            continue

        try:
            record = apply_install(plan, options, state)
        except AppimoError as exc:
            failures += 1
            if args.json:
                results.append({"source": str(source), "ok": False, "error": exc.message})
            else:
                out.blank()
                out.error(exc.message, exc.hint)
                out.note("nothing was changed")
            continue

        if args.json:
            results.append({"source": str(source), "ok": True, **record.to_dict()})
        else:
            out.blank()
            for label, value in plan.summary():
                out.row(label, pretty_path(value) if "/" in str(value) else value)
            for warning in plan.warnings:
                out.warn(warning)
            if plan.replaced:
                out.note(f"replaced the previous integration of {plan.replaced.name}")
            out.blank()
            out.done(f'Launch "{record.name}" from your start menu')

    if args.json:
        print(json.dumps({"ok": failures == 0, "results": results}, indent=2))
    return 1 if failures else 0


def cmd_list(args: argparse.Namespace, out: Out) -> int:
    state = State.load()
    apps = state.all()

    if args.json:
        print(json.dumps({"ok": True, "apps": [a.to_dict() for a in apps]}, indent=2))
        return 0

    if not apps:
        out.blank()
        out.note("nothing integrated yet")
        out.note("try: appimo install ~/Downloads/Some.AppImage")
        return 0

    width = max(len(a.name) for a in apps)
    width = min(max(width, 4), 32)
    out.blank()
    header = f"  {out.paint('NAME'.ljust(width), 'dim')}  {out.paint('MODE'.ljust(8), 'dim')}{out.paint('LAUNCHER', 'dim')}"
    print(header, file=out.stream)
    for app in apps:
        mode = "unpacked" if app.mode == MODE_EXTRACT else "kept"
        name = app.name if len(app.name) <= width else app.name[: width - 1] + "…"
        print(
            f"  {name.ljust(width)}  {mode.ljust(8)}{pretty_path(app.managed_path)}",
            file=out.stream,
        )
    out.blank()
    out.note(f"{len(apps)} application{'s' if len(apps) != 1 else ''} integrated")
    return 0


def cmd_remove(args: argparse.Namespace, out: Out) -> int:
    state = State.load()
    removals: list[dict[str, Any]] = []
    failures = 0

    for key in args.targets:
        try:
            plan = plan_remove(key, keep_files=args.keep_files, state=state)
        except AppimoError as exc:
            failures += 1
            if args.json:
                removals.append({"target": key, "ok": False, "error": exc.message})
            else:
                out.blank()
                out.error(exc.message, exc.hint)
            continue

        if args.dry_run:
            if not args.json:
                out.blank()
                for label, path in plan.actions:
                    out.row(label, pretty_path(path))
                out.note("dry run — nothing was removed")
            else:
                removals.append(
                    {"target": key, "ok": True, "dry_run": True, "id": plan.app.id}
                )
            continue

        try:
            apply_remove(plan, keep_files=args.keep_files, state=state)
        except AppimoError as exc:
            failures += 1
            if args.json:
                removals.append({"target": key, "ok": False, "error": exc.message})
            else:
                out.error(exc.message, exc.hint)
            continue

        if args.json:
            removals.append({"target": key, "ok": True, "id": plan.app.id})
        else:
            out.blank()
            for label, path in plan.actions:
                out.row(label, pretty_path(path))
            out.blank()
            detail = "kept the application file" if args.keep_files else "removed everything"
            out.done(f'Removed "{plan.app.name}" ({detail})')

    if args.json:
        print(json.dumps({"ok": failures == 0, "results": removals}, indent=2))
    return 1 if failures else 0


def cmd_doctor(args: argparse.Namespace, out: Out) -> int:
    checks = doctor.environment_checks()
    if args.path:
        checks = doctor.bundle_checks(Path(args.path)) + checks

    if args.json:
        payload = [
            {"status": c.status, "label": c.label, "detail": c.detail, "hint": c.hint}
            for c in checks
        ]
        print(json.dumps({"ok": not any(c.status == doctor.FAIL for c in checks), "checks": payload}, indent=2))
        return 1 if any(c.status == doctor.FAIL for c in checks) else 0

    out.blank()
    for check in checks:
        status = out.paint(check.status.upper().ljust(5), _STATUS_COLOUR[check.status])
        print(f"  {status} {check.label.ljust(22)}{check.detail}", file=out.stream)
        if check.hint:
            out.note(f"        {' ' * 23}{check.hint}")
    out.blank()
    return 1 if any(c.status == doctor.FAIL for c in checks) else 0


def cmd_info(args: argparse.Namespace, out: Out) -> int:
    """Show what Appimo found inside a bundle without changing anything."""
    source = Path(args.path).expanduser()
    try:
        bundle = inspect(source, unsafe_extract=args.unsafe_extract, timeout=args.timeout)
    except AppimoError as exc:
        out.error(exc.message, exc.hint)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "source": str(bundle.source),
                    "kind": bundle.kind,
                    "offset": bundle.offset,
                    "name": bundle.metadata.name,
                    "comment": bundle.metadata.comment,
                    "categories": bundle.metadata.categories,
                    "mime_types": bundle.metadata.mime_types,
                    "terminal": bundle.metadata.terminal,
                    "exec_arguments": bundle.metadata.exec_arguments,
                    "icon": bundle.best_icon().member if bundle.best_icon() else None,
                    "icons": [
                        {"member": c.member, "kind": c.kind, "size": c.size, "score": c.score}
                        for c in bundle.icons
                    ],
                    "members": len(bundle.members),
                },
                indent=2,
            )
        )
        return 0

    meta = bundle.metadata
    out.blank()
    out.row("reading", bundle.source.name)
    out.row("kind", f"{bundle.kind} (squashfs at byte {bundle.offset})")
    out.row("name", meta.name)
    if meta.comment:
        out.row("comment", meta.comment)
    if meta.categories:
        out.row("categories", ", ".join(meta.categories))
    if meta.mime_types:
        out.row("mime", ", ".join(meta.mime_types))
    out.row("terminal", "yes" if meta.terminal else "no")
    if meta.exec_arguments:
        out.row("arguments", " ".join(meta.exec_arguments))
    out.row("members", str(len(bundle.members)))

    icon = bundle.best_icon()
    out.row("icon", icon.described + f"  ({icon.member})" if icon else "none found")
    if len(bundle.icons) > 1:
        out.note(f"{len(bundle.icons)} icon candidates; best is listed above")
    out.blank()
    return 0


def cmd_gui(args: argparse.Namespace, out: Out) -> int:
    try:
        from .gui.app import run
    except ImportError as exc:  # pragma: no cover - optional dependency
        out.error(
            f"the graphical interface needs Flet ({exc})",
            hint="re-run the installer, or: pipx install 'appimo[gui]'",
        )
        return 1
    return run()


def cmd_menu(args: argparse.Namespace, out: Out) -> int:
    if args.remove:
        if menu.remove_own_launcher():
            out.done("Removed Appimo's own start-menu entry")
        else:
            out.note("Appimo's start-menu entry was not installed")
        return 0

    path, warnings = menu.install_own_launcher(force=args.force)
    out.row("launcher", str(path))
    out.row("icon", menu.APP_ID)
    for warning in warnings:
        out.warn(warning)
    out.done("Appimo is now in your start menu")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="appimo",
        description="Turn any AppImage into a real, installed application.",
        epilog="Run 'appimo doctor' if something isn't working.",
    )
    parser.add_argument("--version", action="version", version=f"appimo {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--json", action="store_true", help="machine-readable output")
        sub.add_argument("--dry-run", action="store_true", help="show what would change")

    install = subparsers.add_parser(
        "install", aliases=["add", "integrate"], help="integrate one or more AppImages"
    )
    install.add_argument("paths", nargs="+", metavar="PATH", help="AppImage, SquashFS or AppDir")
    install.add_argument("--id", help="launcher id (default: dev.appimo.<name>)")
    install.add_argument("--name", help="override the application name")
    install.add_argument("--dir", help="where to keep the managed application")
    install.add_argument(
        "--extract",
        action="store_true",
        help="unpack instead of keeping the AppImage (for systems without FUSE)",
    )
    install.add_argument("--copy", action="store_true", help="copy instead of moving the file")
    install.add_argument("--force", action="store_true", help="replace an existing integration")
    install.add_argument("--no-icon", action="store_true", help="do not install an icon")
    install.add_argument(
        "--unsafe-extract",
        action="store_true",
        help="run the bundle's own runtime when it cannot be read directly",
    )
    install.add_argument("--timeout", type=int, default=300, help=argparse.SUPPRESS)
    add_common(install)

    listing = subparsers.add_parser("list", aliases=["ls"], help="show integrated applications")
    listing.add_argument("--json", action="store_true", help="machine-readable output")

    remove = subparsers.add_parser(
        "remove", aliases=["rm", "uninstall"], help="remove integrated applications"
    )
    remove.add_argument("targets", nargs="+", metavar="NAME", help="name or id")
    remove.add_argument(
        "--keep-files", action="store_true", help="remove the launcher but keep the app file"
    )
    add_common(remove)

    info = subparsers.add_parser("info", help="describe a bundle without changing anything")
    info.add_argument("path", metavar="PATH")
    info.add_argument("--unsafe-extract", action="store_true")
    info.add_argument("--timeout", type=int, default=300, help=argparse.SUPPRESS)
    info.add_argument("--json", action="store_true")

    doc = subparsers.add_parser("doctor", help="check the environment")
    doc.add_argument("path", nargs="?", metavar="PATH", help="also inspect this bundle")
    doc.add_argument("--json", action="store_true")

    submenu = subparsers.add_parser(
        "menu", help="add Appimo itself to your start menu"
    )
    submenu.add_argument(
        "--force", action="store_true", help="refresh an existing launcher"
    )
    submenu.add_argument(
        "--remove", action="store_true", help="remove the launcher again"
    )

    subparsers.add_parser("gui", help="start the graphical interface")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    out = Out()

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "install": cmd_install,
        "add": cmd_install,
        "integrate": cmd_install,
        "list": cmd_list,
        "ls": cmd_list,
        "remove": cmd_remove,
        "rm": cmd_remove,
        "uninstall": cmd_remove,
        "info": cmd_info,
        "doctor": cmd_doctor,
        "menu": cmd_menu,
        "gui": cmd_gui,
    }
    try:
        return handlers[args.command](args, out)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        out.error("interrupted")
        return 130
    except AppimoError as exc:
        out.error(exc.message, exc.hint)
        return 1
