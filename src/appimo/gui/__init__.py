"""The Appimo graphical interface (Flet).

The GUI is a thin shell over `appimo.installer`: it builds an `InstallPlan`,
shows the user exactly what that plan will change, and only then applies it.
No installation logic lives here.
"""

from .app import App, main, run

__all__ = ["App", "main", "run"]
