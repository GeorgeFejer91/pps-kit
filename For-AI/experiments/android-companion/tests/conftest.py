"""Experiment-only compatibility imports for the retired public Android namespace."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import peripersonal_space_toolkit


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = EXPERIMENT_ROOT / "python"
VALIDATION_ROOT = EXPERIMENT_ROOT / "validation"

sys.path.insert(0, str(VALIDATION_ROOT))


def _load_experiment_module(name: str) -> None:
    qualified_name = f"peripersonal_space_toolkit.{name}"
    if qualified_name in sys.modules:
        return
    path = PYTHON_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Android experiment module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    setattr(peripersonal_space_toolkit, name, module)
    spec.loader.exec_module(module)


for _module_name in (
    "android_lsl_admin",
    "android_lsl_monitor",
    "mobile_phone_runtime",
    "mobile_pps_replication",
    "runner_companion",
):
    _load_experiment_module(_module_name)
