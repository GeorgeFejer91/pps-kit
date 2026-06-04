from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "tools" / "release_audit.py"

spec = importlib.util.spec_from_file_location("release_audit", AUDIT_PATH)
assert spec is not None and spec.loader is not None
release_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_audit)


def test_release_audit_passes():
    assert release_audit.run_audit() == []
