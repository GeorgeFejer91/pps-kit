"""Helpers for packaged application visual assets."""

from __future__ import annotations

import ctypes
import sys
from importlib.resources import files
from typing import Any


def package_asset(name: str) -> Any:
    """Return a traversable packaged asset path."""
    return files("peripersonal_space_toolkit.assets").joinpath(name)


def apply_qt_app_icon(qt: dict[str, Any], *, app: Any | None = None, window: Any | None = None) -> Any | None:
    """Apply the packaged PPS icon to a Qt app/window when QIcon is available."""
    q_icon = qt.get("QIcon")
    if q_icon is None:
        return None
    icon = None
    for filename in ("pps_toolkit_icon.ico", "pps_toolkit_icon.png"):
        candidate = q_icon(str(package_asset(filename)))
        if not candidate.isNull():
            icon = candidate
            break
    if icon is None:
        return None
    if app is not None:
        app.setWindowIcon(icon)
    if window is not None:
        window.setWindowIcon(icon)
    return icon


def set_windows_app_user_model_id(app_id: str = "PPS.Toolkit.App") -> None:
    """Set a stable Windows AppUserModelID for taskbar icon grouping."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        return
