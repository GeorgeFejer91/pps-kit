#!/usr/bin/env python
"""Validate the Qt/PySide runtime used by PPS runner packaging."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _fail(message: str) -> int:
    print(f"Qt runtime check failed: {message}", file=sys.stderr)
    return 1


def check_importable_qt() -> int:
    try:
        from PySide6.QtCore import QLibraryInfo
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except Exception as exc:
        return _fail(
            "PySide6.QtCore/QtWidgets could not be imported. "
            "Reinstall the pinned GUI dependency with: python -m pip install -e .[gui]\n"
            f"Import error: {exc}"
        )

    plugins_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    qwindows = plugins_path / "platforms" / "qwindows.dll"
    if not qwindows.is_file():
        return _fail(f"Windows Qt platform plugin is missing: {qwindows}")
    print(f"Qt import ok; platform plugin found: {qwindows}")
    return 0


def check_packaged_runner(root: Path) -> int:
    runner = root / "PPSExperimentRunner.exe"
    internal = root / "_internal"
    required = [
        runner,
        internal / "PySide6" / "Qt6Core.dll",
        internal / "PySide6" / "Qt6Gui.dll",
        internal / "PySide6" / "Qt6Widgets.dll",
        internal / "PySide6" / "plugins" / "platforms" / "qwindows.dll",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        return _fail("Packaged runner is missing required Qt files:\n" + "\n".join(f"  {path}" for path in missing))
    print(f"Packaged Qt runtime ok: {root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packaged-runner", type=Path, default=None, help="Path to dist/PPSExperimentRunner to validate.")
    args = parser.parse_args(argv)

    status = check_importable_qt()
    if status != 0:
        return status
    if args.packaged_runner is not None:
        return check_packaged_runner(args.packaged_runner.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
