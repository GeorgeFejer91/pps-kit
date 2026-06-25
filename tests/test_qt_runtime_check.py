from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "check_qt_runtime.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_qt_runtime", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packaged_runner_check_rejects_missing_qwindows(tmp_path: Path):
    module = _load_module()
    root = tmp_path / "PPSExperimentRunner"
    py_side = root / "_internal" / "PySide6"
    py_side.mkdir(parents=True)
    (root / "PPSExperimentRunner.exe").write_bytes(b"exe")
    (py_side / "Qt6Core.dll").write_bytes(b"core")
    (py_side / "Qt6Gui.dll").write_bytes(b"gui")
    (py_side / "Qt6Widgets.dll").write_bytes(b"widgets")

    assert module.check_packaged_runner(root) == 1


def test_packaged_runner_check_accepts_qwindows(tmp_path: Path):
    module = _load_module()
    root = tmp_path / "PPSExperimentRunner"
    py_side = root / "_internal" / "PySide6"
    platforms = py_side / "plugins" / "platforms"
    platforms.mkdir(parents=True)
    (root / "PPSExperimentRunner.exe").write_bytes(b"exe")
    (py_side / "Qt6Core.dll").write_bytes(b"core")
    (py_side / "Qt6Gui.dll").write_bytes(b"gui")
    (py_side / "Qt6Widgets.dll").write_bytes(b"widgets")
    (platforms / "qwindows.dll").write_bytes(b"plugin")

    assert module.check_packaged_runner(root) == 0
