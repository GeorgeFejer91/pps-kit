"""PyInstaller entrypoint for the PPS Experiment Runner."""

from __future__ import annotations

from peripersonal_space_toolkit.focus_app import main


if __name__ == "__main__":
    raise SystemExit(main())
