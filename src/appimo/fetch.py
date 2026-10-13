"""Downloading bundles over HTTP(S).

Part of the core with no third-party dependencies: `urllib` covers it. Only
`https` is allowed, only `200 OK` is accepted, and the download streams to a
temporary file so a half-finished transfer never gets integrated by mistake.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib import error as urllib_error
from urllib.request import Request, urlopen

from .errors import AppimoError

CHUNK = 256 * 1024
MAX_REDIRECTS = 5


def _open(url: str):
    """Open one URL, refusing anything that is not https."""
    if not url.lower().startswith("https://"):
        raise AppimoError(
            f"only https URLs can be downloaded (got {url.split(':')[0] or 'no scheme'})",
            hint="download the AppImage manually and run 'appimo install <file>' instead",
        )
    request = Request(url, headers={"User-Agent": f"appimo (+https://appimo.dev)"})
    return urlopen(request, timeout=60)


def fetch(
    url: str,
    destination: Path | None = None,
    *,
    expected_sha256: str = "",
    progress=None,
) -> Path:
    """Download `url` to a file.

    With no `destination`, a temporary file is created and the caller owns
    deleting it. `progress(done, total)` is called as the transfer runs (total
    can be None when the server sends no length). The SHA-256 of the payload
    is returned via the companion `sha256_of`, and `expected_sha256` verifies
    the download against a recorded hash before it is trusted.
    """
    destination_dir = destination.parent if destination else Path(tempfile.gettempdir())
    destination_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = _open(url)
    except urllib_error.HTTPError as exc:
        raise AppimoError(
            f"the server replied {exc.code} for {url}",
            hint="check the URL, or download the file manually",
        ) from exc
    except urllib_error.URLError as exc:
        raise AppimoError(
            f"could not reach {url.split('/')[2] if '://' in url else url}",
            hint=f"network problem: {exc.reason}",
        ) from exc

    digest = hashlib.sha256()
    tmp = Path(
        tempfile.NamedTemporaryFile(
            prefix="appimo-", suffix=".download", dir=destination_dir, delete=False
        ).name
    )
    try:
        total = response.headers.get("Content-Length")
        total = int(total) if total else None
        done = 0
        with tmp.open("wb") as stream:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                stream.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except BaseException:
        tmp.unlink(missing_ok=True)
        response.close()
        raise

    actual = digest.hexdigest()
    if expected_sha256 and actual != expected_sha256.lower():
        tmp.unlink(missing_ok=True)
        raise AppimoError(
            f"the download's checksum changed (was {expected_sha256[:12]}…, now {actual[:12]}…)",
            hint="upstream replaced the file; re-run with --refresh to accept the new build",
        )
    response.close()

    if destination is None:
        return tmp
    shutil.move(str(tmp), str(destination))
    return destination


def sha256_of(path: Path) -> str:
    """The hex SHA-256 of a file, read in chunks (AppImages are large)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
