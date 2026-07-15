from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_ready_profile_expected_contrast_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_ready_profile_expected_contrast_audit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_ready_profile_expected_contrast_audit_reports_supported_and_missing_contrasts(tmp_path: Path):
    audit = _load_script()
    rows_path = tmp_path / "roussel_analysis_ready_trials.csv"
    _write_csv(
        rows_path,
        [
            {
                "row_label": "DynaSpace looming source",
                "respiratory_phase": "DynaSpace looming source",
                "family": "audio_tactile",
                "soa_ms": "105",
            },
            {
                "row_label": "DynaSpace fixed 640 cm source",
                "respiratory_phase": "DynaSpace fixed 640 cm source",
                "family": "audio_tactile",
                "soa_ms": "105",
            },
        ],
    )
    smoke_path = tmp_path / "runner_smoke.json"
    smoke_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "template_id": "roussel_2025_dynaspace_mobile_pps",
                        "outputs": {"analysis_ready_trials": str(rows_path)},
                    },
                    {
                        "template_id": "noel_2015_bodily_self",
                        "outputs": {"analysis_ready_trials": str(tmp_path / "missing.csv")},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "smartphone_rt_methods_2025",
                        "citation_short": "Roussel 2025",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["roussel_2025_dynaspace_mobile_pps"],
                        "expected_outcome": {"expected_effect_direction": "looming_faster_than_static"},
                    },
                    {
                        "record_id": "noel_2015_bodily_self",
                        "citation_short": "Noel 2015",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["noel_2015_bodily_self"],
                        "expected_outcome": {
                            "expected_effect_direction": "synchronous_front_expansion_and_back_reduction"
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = audit.run_audit(
        ledger_path=ledger_path,
        runner_smoke_report=smoke_path,
        output_dir=tmp_path / "audit",
    )

    assert report["schema"] == audit.SCHEMA
    assert report["passed"]
    assert report["summary"] == {
        "ready_profile_record_count": 2,
        "synthetic_comparison_record_count": 1,
        "synthetic_comparison_passed_count": 1,
        "synthetic_comparison_failed_count": 0,
        "contrast_metadata_blocked_record_count": 1,
        "contrast_metadata_present_model_missing_record_count": 0,
    }
    by_id = {row["record_id"]: row for row in report["records"]}
    smartphone = by_id["smartphone_rt_methods_2025"]
    assert smartphone["status"] == "synthetic_behavioral_comparison_passed"
    assert smartphone["synthetic_comparison"]["fixed_minus_looming_ms"] == 25.0
    assert Path(smartphone["synthetic_comparison"]["synthetic_rows_csv"]).is_file()

    noel = by_id["noel_2015_bodily_self"]
    assert noel["status"] == "contrast_metadata_missing"
    assert noel["missing_contrasts"] == ["stroking_synchrony", "front_back_space"]
    assert "Propagate stroking_synchrony, front_back_space" in noel["required_next_step"]
