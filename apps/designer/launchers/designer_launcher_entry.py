"""Windowed PyInstaller entry point for PPS Experiment Designer."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _configure_windowed_streams() -> None:
    if not getattr(sys, "frozen", False) or (sys.stdout is not None and sys.stderr is not None):
        return
    state_root = Path(os.environ.get("PPS_DESIGNER_STATE_ROOT", Path.home() / ".pps-toolkit"))
    state_root.mkdir(parents=True, exist_ok=True)
    stream = (state_root / "designer-launch.log").open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


if __name__ == "__main__":
    _configure_windowed_streams()
    try:
        from peripersonal_space_toolkit.designer_shell import main

        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise
