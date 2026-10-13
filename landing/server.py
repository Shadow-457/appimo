#!/usr/bin/env python3
"""Tiny static server for the Appimo landing page, with custom error pages.

Usage:
    python3 landing/server.py

Serves landing/ on http://127.0.0.1:8778 with:
  - 200 for real files
  - 404 -> landing/404.html
  - other error statuses -> landing/<code>.html when one exists
  - /203, /403, /500 ... preview their pages directly (trailing slash optional)
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
PORT = 8778
HOST = "127.0.0.1"

mimetypes.init()
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/vnd.microsoft.icon", ".ico")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"

        # Preview route: /203, /403, /500 ... render that status page directly.
        if len(path) > 1 and path[1:].isdigit() and len(path) == 4:
            page = ROOT / f"{path[1:]}.html"
            if page.is_file():
                self._serve(page, int(path[1:]))
                return

        # The index, an explicit real file, or a directory's index.
        if path == "/":
            self._serve(ROOT / "index.html", 200)
            return

        # Real file?
        candidate = ROOT / path.strip("/")
        if candidate.is_file():
            self._serve(candidate, 200)
            return

        directory = ROOT / path.strip("/") / "index.html"
        if directory.is_file():
            self._serve(directory, 200)
            return

        # Everything else -> 404
        self._serve(ROOT / "404.html", 404)

    def send_error(self, code, message=None, explain=None):
        """Replace the server's built-in plain-text error page with ours."""
        page = ROOT / f"{code}.html"
        if page.is_file():
            if self.command == "HEAD":
                self.send_response(code)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(page.stat().st_size))
                self.end_headers()
                return
            self._serve(page, code)
            return
        super().send_error(code, message, explain)

    def _serve(self, file: Path, status: int) -> None:
        ct = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        try:
            data = file.read_bytes()
        except OSError:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # Quiet by default; pass --verbose to the server to see requests.
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"http://127.0.0.1:{PORT}/", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(file=sys.stderr)
        server.server_close()
