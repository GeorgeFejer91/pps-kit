"""PyInstaller entrypoint for the PPS local dashboard companion."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


_LOG_ROOT: Path | None = None
_STREAM_HANDLES = []


def _configure_frozen_root() -> None:
    if not getattr(sys, "frozen", False):
        return
    executable_dir = Path(sys.executable).resolve().parent
    if executable_dir.parent.name.lower() == "dist":
        root = executable_dir.parent.parent
    else:
        root = executable_dir
    os.environ.setdefault("PPS_TOOLKIT_ROOT", str(root))
    os.chdir(root)
    global _LOG_ROOT
    _LOG_ROOT = root
    _ensure_frozen_streams(root)


def _ensure_frozen_streams(root: Path) -> None:
    log_dir = root / "local_data" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(sys.executable).resolve().parent
    if sys.stdout is None:
        stdout_handle = (log_dir / "pps_dashboard_launcher_stream.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = stdout_handle
        _STREAM_HANDLES.append(stdout_handle)
    if sys.stderr is None:
        stderr_handle = (log_dir / "pps_dashboard_launcher_stream.log").open("a", encoding="utf-8", buffering=1)
        sys.stderr = stderr_handle
        _STREAM_HANDLES.append(stderr_handle)


def _write_frozen_log(message: str) -> None:
    if not getattr(sys, "frozen", False):
        return
    root = _LOG_ROOT or Path(os.environ.get("PPS_TOOLKIT_ROOT", Path(sys.executable).resolve().parent))
    try:
        log_dir = root / "local_data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with (log_dir / "pps_dashboard_launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except OSError:
        return


def _main() -> int:
    _write_frozen_log(f"startup cwd={Path.cwd()} argv={sys.argv!r}")
    from peripersonal_space_toolkit.dashboard_app import main

    _write_frozen_log("imported dashboard_app; entering main")
    return main()


_configure_frozen_root()


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except Exception:
        _write_frozen_log("fatal exception:\n" + traceback.format_exc())
        raise
