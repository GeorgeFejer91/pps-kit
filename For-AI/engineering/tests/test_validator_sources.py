"""Paper-specific validators must resolve the tracked source they validate."""

import json
import runpy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "For-AI" / "engineering" / "validation" / "scripts"


@pytest.mark.parametrize(
    "script",
    [path for path in sorted(SCRIPTS.glob("run_*known_parameter_profile_validation.py"))
     if "MANUAL_REVIEW =" in path.read_text(encoding="utf-8")],
    ids=lambda path: path.stem,
)
def test_validator_source_review_is_available(script: Path) -> None:
    namespace = runpy.run_path(str(script))
    review_path = namespace["MANUAL_REVIEW"]
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["record_id"] == namespace.get("RECORD_ID", namespace.get("TEMPLATE_ID"))
