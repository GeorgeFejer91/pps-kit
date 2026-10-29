from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = ROOT / "For-AI" / "engineering" / "release" / "tools" / "release_audit.py"

spec = importlib.util.spec_from_file_location("release_audit", AUDIT_PATH)
assert spec is not None and spec.loader is not None
release_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_audit)


def test_release_audit_passes():
    assert release_audit.run_audit() == []


def test_template_audit_distinguishes_soa_only_from_missing_paired_distance(tmp_path, monkeypatch):
    templates = tmp_path / "packages" / "pps-resources" / "study_templates"
    templates.mkdir(parents=True)
    template = {
        "template_id": "timing", "title": "Timing", "citation": "Source",
        "source_url": "https://example.org/source", "verification_status": "partial",
        "design": {"protocol": {"soa_values_ms": [250], "spatial_values_cm": [], "pair_spatial_values_with_soas": False}},
    }
    for number in range(15):
        (templates / f"{number}.json").write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(release_audit, "REPO_ROOT", tmp_path)
    assert release_audit.check_study_templates() == []
    template["design"]["protocol"]["pair_spatial_values_with_soas"] = True
    (templates / "0.json").write_text(json.dumps(template), encoding="utf-8")
    assert len(release_audit.check_study_templates()) == 1
    assert "missing protocol spatial values" in release_audit.check_study_templates()[0]
