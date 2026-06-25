"""Subprocess launch helpers shared by native GUI entry points."""

from __future__ import annotations

import os
import subprocess
from typing import Any


def windows_no_console_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return subprocess kwargs that suppress helper console windows on Windows."""

    kwargs = dict(overrides)
    if os.name != "nt":
        return kwargs
    no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    if not no_window:
        return kwargs
    existing_flags = int(kwargs.get("creationflags") or 0)
    kwargs["creationflags"] = existing_flags | no_window
    return kwargs
