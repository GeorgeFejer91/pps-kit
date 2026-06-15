"""PyInstaller entrypoint for the PPS Experiment Runner."""

from __future__ import annotations

import os


# The packaged runner must enable python-sounddevice's ASIO PortAudio backend
# before any module can import sounddevice. The native Komplete Audio ASIO route
# is the validated 3+ channel timing path for PPS experiments.
os.environ.setdefault("SD_ENABLE_ASIO", "1")


def _enable_windows_dpi_awareness() -> None:
    """Align Qt global positions with Win32 mouse coordinates for validation."""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


_enable_windows_dpi_awareness()

from peripersonal_space_toolkit.focus_app import main


if __name__ == "__main__":
    raise SystemExit(main())
