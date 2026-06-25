#!/usr/bin/env python
"""Verify the bundled Pfeiffer-style profile and render handoff."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from peripersonal_space_toolkit.design import DEFAULT_SOFA_FILE  # noqa: E402
from peripersonal_space_toolkit.render_backend import build_render_config, render_design_with_3dti  # noqa: E402
from peripersonal_space_toolkit.templates import load_templates  # noqa: E402


PFEIFFER_TEMPLATE_ID = "pfeiffer_2018_lateral_perihead_left_to_right"


def _approx(actual: float, expected: float, tolerance: float, label: str, problems: list[str]) -> None:
    if not math.isclose(actual, expected, abs_tol=tolerance):
        problems.append(f"{label}: expected {expected}, got {actual}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verify(output_dir: Path, *, seed: int, engine: str) -> tuple[dict, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    templates = load_templates(REPO_ROOT / "study_templates")
    template = next((item for item in templates if item.template_id == PFEIFFER_TEMPLATE_ID), None)
    if template is None:
        return {}, [f"Missing study template: {PFEIFFER_TEMPLATE_ID}"]

    design = template.design
    problems: list[str] = []
    _approx(design.trajectory.start_x_m, -0.4, 1e-9, "start_x_m", problems)
    _approx(design.trajectory.end_x_m, 0.4, 1e-9, "end_x_m", problems)
    _approx(design.trajectory.start_y_m, 0.05, 1e-9, "start_y_m", problems)
    _approx(design.trajectory.end_y_m, 0.05, 1e-9, "end_y_m", problems)
    _approx(design.trajectory.start_z_m, 0.0, 1e-9, "start_z_m", problems)
    _approx(design.trajectory.end_z_m, 0.0, 1e-9, "end_z_m", problems)
    _approx(design.trajectory.movement_duration_s, 4.0, 1e-9, "movement_duration_s", problems)
    _approx(design.trajectory.propagation_speed_mps, 0.2, 1e-9, "propagation_speed_mps", problems)
    if design.noises[0].noise_type != "pink":
        problems.append(f"noise_type: expected pink, got {design.noises[0].noise_type}")
    if design.sofa_file != DEFAULT_SOFA_FILE:
        problems.append(f"sofa_file should remain the hidden standardized default: {design.sofa_file}")

    config = build_render_config(design, seed=seed, output_dir=output_dir)
    for event in config["tactile"]["events"]:
        if not math.isclose(
            float(event["planned_spatial_value_cm"]),
            float(event["source_radius_at_tactile_cm"]),
            abs_tol=1e-5,
        ):
            problems.append(
                "SOA/spatial mismatch: "
                f"SOA {event['soa_ms']} planned {event['planned_spatial_value_cm']} cm, "
                f"actual {event['source_radius_at_tactile_cm']} cm"
            )

    result = render_design_with_3dti(
        REPO_ROOT / "study_templates" / f"{PFEIFFER_TEMPLATE_ID}.json",
        output_dir,
        seed=seed,
        engine=engine,
    )
    if result.status not in {"rendered_3dti", "rendered_reference"}:
        problems.append(f"render status should be rendered_3dti or rendered_reference, got {result.status}")
    if not result.wav_paths:
        problems.append("render did not produce a WAV path")

    qc_rows = _read_csv(result.qc_path) if result.qc_path.exists() else []
    tactile_rows = _read_csv(result.tactile_events_path) if result.tactile_events_path and result.tactile_events_path.exists() else []
    if qc_rows:
        row = qc_rows[0]
        try:
            first_left = float(row["first_half_left_rms"])
            first_right = float(row["first_half_right_rms"])
            second_left = float(row["second_half_left_rms"])
            second_right = float(row["second_half_right_rms"])
            if not first_left > first_right:
                problems.append("first half should be left-ear dominant for Pfeiffer left-to-right profile")
            if not second_right > second_left:
                problems.append("second half should be right-ear dominant for Pfeiffer left-to-right profile")
        except (KeyError, ValueError):
            if result.status == "rendered_reference":
                problems.append("reference-render QC did not include left/right RMS fields")

    report = {
        "schema": "pps-pfeiffer-profile-verification.v1",
        "template_id": PFEIFFER_TEMPLATE_ID,
        "render_status": result.status,
        "render_engine": "native-3dti" if result.status == "rendered_3dti" else "python-sofa-reference",
        "seed": seed,
        "design_parameters": {
            "noise_type": design.noises[0].noise_type,
            "sample_rate": config["source"]["sample_rate"],
            "start_x_m": design.trajectory.start_x_m,
            "end_x_m": design.trajectory.end_x_m,
            "front_offset_y_m": design.trajectory.start_y_m,
            "z_m": design.trajectory.start_z_m,
            "movement_duration_s": design.trajectory.movement_duration_s,
            "speed_mps": design.trajectory.propagation_speed_mps,
            "sofa_file": design.sofa_file,
        },
        "soa_tactile_events": tactile_rows,
        "qc_rows": qc_rows,
        "wav_paths": [str(path) for path in result.wav_paths],
        "manifest_path": str(result.manifest_path),
        "problems": problems,
    }
    report_path = output_dir / "pfeiffer_verification_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "pfeiffer_verification")
    parser.add_argument("--seed", type=int, default=2018)
    parser.add_argument("--engine", choices=["auto", "native-3dti", "python-sofa-reference"], default="auto")
    args = parser.parse_args(argv)

    report, problems = verify(args.output_dir, seed=args.seed, engine=args.engine)
    report_path = args.output_dir / "pfeiffer_verification_report.json"
    if problems:
        print(f"Pfeiffer verification failed; report: {report_path}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"Pfeiffer verification passed; report: {report_path}")
    print(f"Render status: {report.get('render_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
