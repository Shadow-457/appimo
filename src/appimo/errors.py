"""Exceptions raised by Appimo.

Every failure carries a short, actionable message: the CLI prints these as a
single line with a suggested fix, never a traceback.
"""

from __future__ import annotations


class AppimoError(Exception):
    """Base class. `hint` is the one-line "what to do about it"."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class NotAnAppImage(AppimoError):
    """The input file is not an AppImage, a SquashFS image, or an AppDir."""


class UnreadableBundle(AppimoError):
    """The bundle is recognised but its contents could not be read."""


class NoDesktopEntry(AppimoError):
    """The bundle contains no usable .desktop file to derive metadata from."""


class AlreadyInstalled(AppimoError):
    """Something with this id is already integrated."""


class NotInstalled(AppimoError):
    """Nothing with this id is integrated."""


class RefusedAsRoot(AppimoError):
    """Appimo writes to the invoking user's home; running as root is refused."""
