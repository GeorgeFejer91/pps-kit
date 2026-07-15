"""Synthetic expected-vs-observed outcome smoke test for ready profiles.

This validation harness exercises the comparison/reporting contract for the
runnable published profiles in the audiotactile expected-outcome ledger. It
uses a deterministic direction-label oracle, not participant data, so it must
not be cited as human PPS replication evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_synthetic_expected_outcome_smoke_20260715"
)

SCHEMA = "pps-synthetic-expected-outcome-smoke.v1"
READY_GAP = "ready_profile_mouse_click_simulated_participant_like_comparison_available_needs_collected_behavioral_comparison"
MODEL_ID = "direction_label_oracle.v1"
EVIDENCE_BOUNDARY = (
    "Synthetic comparison rows are deterministic software checks of the "
    "expected-vs-observed report contract. They are not human behavioral PPS "
    "evidence, not collected participant data, and not publication replication "
    "evidence."
)


def build_report(ledger: dict[str, Any], *, source_ledger: str) -> dict[str, Any]:
    records = [
        record
        for record in ledger.get("records", [])
        if record.get("observed_comparison_gap") == READY_GAP
        and record.get("runnable_status") == "runnable_profile_parameters_ready"
        and record.get("expected_outcome_status") == "structured_expected_outcome_extracted"
    ]
    rows = [_build_row(record) for record in sorted(records, key=lambda item: str(item.get("record_id") or ""))]
    matches = sum(1 for row in rows if row["comparison"]["pass"])
    human_count = int(ledger.get("summary", {}).get("observed_behavioral_comparison_record_count") or 0)
    return {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "source_expected_outcome_ledger": source_ledger,
        "source_expected_outcome_ledger_schema": str(ledger.get("schema") or ""),
        "passed": bool(rows) and matches == len(rows),
        "summary": {
            "ready_profile_record_count": len(records),
            "synthetic_comparison_record_count": len(rows),
            "synthetic_direction_match_count": matches,
            "synthetic_direction_mismatch_count": len(rows) - matches,
            "human_behavioral_comparison_count_from_ledger": human_count,
            "all_synthetic_direction_checks_passed": bool(rows) and matches == len(rows),
        },
        "model": {
            "model_id": MODEL_ID,
            "model_role": "direction-label oracle for expected-vs-observed report plumbing",
            "model_inputs": ["structured expected_outcome.expected_effect_direction"],
            "assumption_boundary": EVIDENCE_BOUNDARY,
        },
        "records": rows,
        "limitations": [
            EVIDENCE_BOUNDARY,
            "The oracle copies the structured expected effect direction into a synthetic observed direction.",
            "A passing smoke report does not estimate effect size, participant variability, tactile perception, or apparatus timing.",
        ],
    }


def run_smoke(*, ledger_path: Path = LEDGER_PATH, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    source = _repo_relative(ledger_path)
    report = build_report(ledger, source_ledger=source)
    write_report(report, output_dir)
    return report


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "synthetic_expected_outcome_smoke_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "synthetic_expected_outcome_smoke_report.md").write_text(
        _markdown_report(report),
        encoding="utf-8",
    )


def _build_row(record: dict[str, Any]) -> dict[str, Any]:
    expected = dict(record.get("expected_outcome") or {})
    expected_direction = str(expected.get("expected_effect_direction") or "")
    observed_direction = expected_direction
    passed = bool(expected_direction) and observed_direction == expected_direction
    return {
        "record_id": str(record.get("record_id") or ""),
        "citation_short": str(record.get("citation_short") or ""),
        "template_ids": [str(value) for value in record.get("current_template_ids") or []],
        "runnable_status": str(record.get("runnable_status") or ""),
        "ledger_observed_vs_expected_status": str(record.get("observed_vs_expected_status") or ""),
        "expected": {
            "primary_expected_effect": str(expected.get("primary_expected_effect") or ""),
            "effect_direction": expected_direction,
            "observable_metric": str(expected.get("observable_metric") or ""),
            "condition_contrast": str(expected.get("condition_contrast") or ""),
            "outcome_family": str(expected.get("outcome_family") or ""),
        },
        "synthetic_observation": {
            "model_id": MODEL_ID,
            "observed_effect_direction": observed_direction,
            "observable_metric": str(expected.get("observable_metric") or ""),
            "condition_contrast": str(expected.get("condition_contrast") or ""),
            "observation_source": "synthetic_direction_label_oracle",
        },
        "comparison": {
            "status": "synthetic_direction_matches_expected" if passed else "synthetic_direction_missing_or_mismatch",
            "pass": passed,
            "criterion": "synthetic observed effect-direction label exactly equals the structured expected label",
        },
        "evidence_boundary": EVIDENCE_BOUNDARY,
    }


def _markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Synthetic Expected Outcome Smoke Report",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Ready profiles compared: `{summary['ready_profile_record_count']}`",
        f"- Synthetic direction matches: `{summary['synthetic_direction_match_count']}`",
        f"- Human behavioral comparisons in source ledger: `{summary['human_behavioral_comparison_count_from_ledger']}`",
        "",
        EVIDENCE_BOUNDARY,
        "",
        "## Records",
        "",
    ]
    for row in report["records"]:
        lines.append(
            "- "
            f"`{row['record_id']}`: `{row['comparison']['status']}` "
            f"for `{row['expected']['effect_direction']}`"
        )
    return "\n".join(lines) + "\n"


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a synthetic expected-vs-observed outcome smoke comparison for runnable PPS profiles."
    )
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = run_smoke(ledger_path=args.ledger, output_dir=args.output_dir)
    print(f"Wrote synthetic expected-outcome smoke report: {args.output_dir / 'synthetic_expected_outcome_smoke_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
