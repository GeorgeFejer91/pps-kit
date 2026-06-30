"""Run mobile-style PPS replication checks on collected PPS CSV data."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.mobile_pps_replication import (  # noqa: E402
    INPUT_KIND_AUTO,
    ReplicationOptions,
    analyze_csv,
    discover_input_csvs,
    parse_soa_distance_map,
    write_outputs,
)


def _dataset_slug(path: Path, index: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("._")
    return f"dataset_{index:03d}_{stem or 'pps_data'}"


def _read_status(summary: dict[str, Any], criterion: str) -> str:
    for row in summary.get("criteria") or []:
        if row.get("criterion") == criterion:
            return str(row.get("status") or "")
    return ""


def _run_one(
    path: Path,
    *,
    output_dir: Path,
    options: ReplicationOptions,
    dataset_index: int,
    multi_dataset: bool,
) -> dict[str, Any]:
    result = analyze_csv(path, options=options)
    target_dir = output_dir / _dataset_slug(path, dataset_index) if multi_dataset else output_dir
    written = write_outputs(result, target_dir)
    return {
        "dataset_index": dataset_index,
        "input_csv": str(path),
        "output_dir": str(target_dir),
        "input_kind": result.input_kind,
        "participant_count": result.sample.get("participants", 0),
        "row_count": result.sample.get("raw_rows", 0),
        "basic_facilitation_replicated": result.summary.get("basic_facilitation_replicated", False),
        "performance_integrity_status": _read_status({"criteria": result.criteria_rows}, "performance_integrity"),
        "facilitation_status": _read_status({"criteria": result.criteria_rows}, "multisensory_facilitation_overall"),
        "approach_gradient_status": result.summary.get("approach_gradient_status", ""),
        "sigmoid_boundary_status": result.summary.get("sigmoid_boundary_status", ""),
        "selected_shape_model": result.summary.get("selected_shape_model", ""),
        "report_md": str(written["report_md"]),
        "summary_json": str(written["summary_json"]),
        "warnings": "; ".join(result.warnings),
        "error": "",
    }


def _write_index(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "mobile_pps_replication_index.csv"
    json_path = output_dir / "mobile_pps_replication_index.json"
    md_path = output_dir / "mobile_pps_replication_index.md"
    fields = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps({"datasets": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Mobile PPS Replication Index", ""]
    if not rows:
        lines.append("- No eligible datasets were analyzed.")
    for row in rows:
        status = "ERROR" if row.get("error") else row.get("facilitation_status", "")
        lines.append(
            f"- `{status}` | `{row.get('input_csv')}` | participants={row.get('participant_count')} | "
            f"gradient={row.get('approach_gradient_status')} | sigmoid={row.get('sigmoid_boundary_status')}"
        )
        if row.get("error"):
            lines.append(f"  - Error: {row.get('error')}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"index_csv": csv_path, "index_json": json_path, "index_md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze collected PPS CSV data for mobile/smartphone-style behavioral PPS replication checks."
    )
    parser.add_argument("--input", type=Path, required=True, help="CSV file or folder to scan for collected PPS CSVs.")
    parser.add_argument(
        "--input-kind",
        choices=["auto", "osf-master", "analysis-ready"],
        default=INPUT_KIND_AUTO,
        help="Input schema for CSV files. Directory scans normally use auto.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "validation_runs" / "mobile_pps_replication_current",
        help="Output folder for reports and CSV summaries.",
    )
    parser.add_argument(
        "--soa-distance-map",
        default="300:100,800:73,1500:50,2200:27,2700:10",
        help="Comma-separated SOA:distance_cm map.",
    )
    parser.add_argument("--min-hit-rate", type=float, default=0.70)
    parser.add_argument("--max-catch-fa-rate", type=float, default=0.30)
    parser.add_argument("--anticipation-ms", type=float, default=200.0)
    parser.add_argument("--outlier-sd", type=float, default=2.5)
    parser.add_argument("--sigmoid-r2-threshold", type=float, default=0.70)
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args(argv)

    options = ReplicationOptions(
        input_kind=args.input_kind,
        soa_distance_map=parse_soa_distance_map(args.soa_distance_map),
        min_hit_rate=args.min_hit_rate,
        max_catch_fa_rate=args.max_catch_fa_rate,
        anticipation_ms=args.anticipation_ms,
        outlier_sd=args.outlier_sd,
        sigmoid_r2_threshold=args.sigmoid_r2_threshold,
        alpha=args.alpha,
    )
    candidates = discover_input_csvs(args.input)
    multi_dataset = len(candidates) != 1 or args.input.is_dir()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        try:
            row = _run_one(
                candidate,
                output_dir=args.output_dir,
                options=options,
                dataset_index=index,
                multi_dataset=multi_dataset,
            )
        except Exception as exc:
            row = {
                "dataset_index": index,
                "input_csv": str(candidate),
                "output_dir": "",
                "input_kind": "",
                "participant_count": "",
                "row_count": "",
                "basic_facilitation_replicated": "",
                "performance_integrity_status": "",
                "facilitation_status": "",
                "approach_gradient_status": "",
                "sigmoid_boundary_status": "",
                "selected_shape_model": "",
                "report_md": "",
                "summary_json": "",
                "warnings": "",
                "error": str(exc),
            }
        index_rows.append(row)
    index_paths = _write_index(index_rows, args.output_dir)
    analyzed = sum(1 for row in index_rows if not row.get("error"))
    failed = sum(1 for row in index_rows if row.get("error"))
    print(f"Analyzed {analyzed} dataset(s); skipped/failed {failed}.")
    print(f"Wrote {index_paths['index_md']}")
    return 0 if analyzed else 2


if __name__ == "__main__":
    raise SystemExit(main())
