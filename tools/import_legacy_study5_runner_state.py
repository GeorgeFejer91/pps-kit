"""Import legacy Study 5 cleaned CSVs into local runner-shaped session folders.

This tool is intentionally local-only. It copies cleaned participant CSV content
into ignored session folders, redacts name-bearing filename fields, writes
runner-shaped analysis CSVs, and marks the session as a legacy import for stress
testing. It does not claim that the imported trials were collected by the PPS
Experiment Runner.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.focus_app import STUDY5_PROFILE_ID, current_runner_session_root, profile_run_setup_manifest_path
from peripersonal_space_toolkit.session_analysis import (
    SessionAnalysisResult,
    _build_data_behavior_review,
    _build_final_outcomes,
    _build_pps_curves,
    _summarize_responses,
    format_analysis_summary,
    write_analysis_csvs,
)
from peripersonal_space_toolkit.session_runner import (
    DEFAULT_DASHBOARD_STATE_ROOT,
    prepare_segment_run_package,
    record_experiment_activity,
    record_prepared_session_queue,
)


@dataclass(frozen=True)
class ImportResult:
    participant_id: str
    source_sha256: str
    source_trial_count: int
    tactile_trial_count: int
    session_dir: Path
    session_manifest: Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="Folder containing cleaned legacy participant CSVs.")
    parser.add_argument("--output-root", type=Path, default=None, help="Runner output root. Defaults to the remembered runner output project.")
    parser.add_argument("--profile-id", default=STUDY5_PROFILE_ID, help="Finished profile whose Segment 6 run setup should be matched.")
    parser.add_argument("--participants", default="", help="Optional comma-separated normalized IDs, e.g. P003,P005.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of participant CSVs to import.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing legacy import files inside prepared packages.")
    args = parser.parse_args(argv)

    source_dir = args.source_dir.expanduser().resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"Source folder not found: {source_dir}")
    run_setup = profile_run_setup_manifest_path(args.profile_id)
    if not run_setup.is_file():
        raise SystemExit(f"Prepared Segment 6 run setup not found for {args.profile_id}: {run_setup}")

    output_root = (args.output_root or current_runner_session_root()).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    selected = {_normalize_participant_id(item.strip()) for item in args.participants.split(",") if item.strip()}
    source_files = _participant_csv_files(source_dir)
    if selected:
        source_files = [path for path in source_files if _participant_from_csv(path) in selected]
    if args.limit > 0:
        source_files = source_files[: args.limit]
    if not source_files:
        raise SystemExit("No participant CSV files found to import.")

    results: list[ImportResult] = []
    for source_csv in source_files:
        result = _import_participant_csv(
            source_csv,
            run_setup_manifest=run_setup,
            output_root=output_root,
            force=args.force,
        )
        results.append(result)
        print(f"Imported {result.participant_id}: {result.source_trial_count} source rows -> {result.session_dir}")

    manifest = {
        "schema": "pps-legacy-study5-import-batch.v1",
        "profile_id": args.profile_id,
        "run_setup_manifest_path": str(run_setup),
        "output_root": str(output_root),
        "imported_at_unix": time.time(),
        "participant_count": len(results),
        "participants": [
            {
                "participant_id": result.participant_id,
                "source_sha256": result.source_sha256,
                "source_trial_count": result.source_trial_count,
                "tactile_trial_count": result.tactile_trial_count,
                "session_dir": str(result.session_dir),
                "session_manifest": str(result.session_manifest),
            }
            for result in results
        ],
        "provenance_note": "Legacy cleaned Study 5 participant CSVs imported for runner stress testing; not runner-native acquisition.",
    }
    manifest_path = output_root / "legacy_study5_import_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {manifest_path}")
    return 0


def _participant_csv_files(source_dir: Path) -> list[Path]:
    files = []
    for path in sorted(source_dir.glob("P*.csv")):
        lower = path.name.lower()
        if lower.startswith("master_") or lower.endswith(".pending.csv"):
            continue
        participant = _participant_from_csv(path)
        if participant:
            files.append(path)
    return files


def _participant_from_csv(path: Path) -> str:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            row = next(reader, {})
    except Exception:
        row = {}
    return _normalize_participant_id(row.get("participant_id") or path.stem.split("_", 1)[0])


def _normalize_participant_id(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("P"):
        number = "".join(ch for ch in text[1:] if ch.isdigit())
        return f"P{int(number):03d}" if number else ""
    number = "".join(ch for ch in text if ch.isdigit())
    return f"P{int(number):03d}" if number else ""


def _import_participant_csv(
    source_csv: Path,
    *,
    run_setup_manifest: Path,
    output_root: Path,
    force: bool,
) -> ImportResult:
    rows = _read_csv(source_csv)
    if not rows:
        raise ValueError(f"No rows in {source_csv}")
    participant = _normalize_participant_id(rows[0].get("participant_id") or source_csv.stem)
    if not participant:
        raise ValueError(f"Could not infer participant ID from {source_csv}")

    package = prepare_segment_run_package(run_setup_manifest, participant, session_root=output_root)
    import_dir = package.session_dir / "legacy_import"
    if import_dir.exists() and not force:
        raise FileExistsError(f"Legacy import already exists for {participant}: {import_dir}. Use --force to overwrite.")
    if import_dir.exists():
        shutil.rmtree(import_dir)
    import_dir.mkdir(parents=True, exist_ok=True)

    source_hash = _sha256(source_csv)
    redacted_rows = [_redact_source_row(row, participant) for row in rows]
    redacted_source = import_dir / f"{participant}_legacy_cleaned_trials.csv"
    _write_rows(redacted_source, redacted_rows)

    response_rows, event_rows = _runner_rows_from_legacy(redacted_rows, participant)
    final_rows = _build_final_outcomes(response_rows)
    summary_rows = _summarize_responses(final_rows or response_rows)
    curve_rows, fit_rows, model_fit_rows, comparison_rows, warnings = _build_pps_curves(final_rows or response_rows)
    result = SessionAnalysisResult(
        response_rows=response_rows,
        final_outcome_rows=final_rows,
        summary_rows=summary_rows,
        curve_rows=curve_rows,
        fit_rows=fit_rows,
        model_fit_rows=model_fit_rows,
        model_comparison_rows=comparison_rows,
        warnings=[*warnings, "Legacy Study 5 CSV import for runner stress testing; not runner-native acquisition."],
    )
    result.data_behavior_rows, result.exploratory_quality_summary = _build_data_behavior_review(result, event_rows)
    outputs = write_analysis_csvs(result, package.session_dir / "analysis", package.session_id)
    _write_timing_qc(outputs["summary"].parent / f"{package.session_id}_timing_qc.csv")
    summary = format_analysis_summary(result)
    (package.session_dir / "analysis_summary.txt").write_text(
        summary + "\n\nLegacy import provenance: cleaned Study 5 CSV import for stress testing only.\n",
        encoding="utf-8",
    )
    _write_events_csv(package.session_dir / "events.csv", event_rows, participant=participant, session_id=package.session_id)
    _write_metadata(package, source_csv, source_hash, redacted_source, len(rows), len(response_rows))

    record_prepared_session_queue(
        participant_id=participant,
        run_setup_manifest_path=run_setup_manifest,
        session_manifest_path=package.manifest_path,
        status="ready",
        message="Prepared package contains legacy imported Study 5 data for stress testing.",
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
    )
    record_experiment_activity(
        "session_prepared",
        template_id=STUDY5_PROFILE_ID,
        run_setup_manifest_path=str(run_setup_manifest),
        session_manifest_path=str(package.manifest_path),
        session_dir=str(package.session_dir),
        participant_id=participant,
        data_source="legacy_import",
    )
    return ImportResult(
        participant_id=participant,
        source_sha256=source_hash,
        source_trial_count=len(rows),
        tactile_trial_count=len(response_rows),
        session_dir=package.session_dir,
        session_manifest=package.manifest_path,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _redact_source_row(row: dict[str, str], participant: str) -> dict[str, str]:
    output = dict(row)
    output["participant_id"] = participant
    output["recording_file"] = f"{participant}_recording.wav"
    return output


def _runner_rows_from_legacy(rows: list[dict[str, str]], participant: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    response_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    event_id = 1
    base_unix = 1_800_000_000.0
    base_mono = 100_000.0

    def add_event(event_type: str, unix_time: float, payload: dict[str, Any]) -> int:
        nonlocal event_id
        current = event_id
        event_id += 1
        events.append(
            {
                "event_id": current,
                "event_type": event_type,
                "unix_time": unix_time,
                "monotonic_time": base_mono + (unix_time - base_unix),
                **payload,
            }
        )
        return current

    add_event("session_start", base_unix, {"participant_id": participant, "data_source": "legacy_import"})
    for index, row in enumerate(rows, start=1):
        trial_type = _clean(row.get("trial_type"))
        part_number = _int(row.get("part_number"), 0)
        block_number = _int(row.get("block_number"), 0)
        trial_number = _int(row.get("trial_number"), index)
        soa_ms = _float(row.get("SOA_ms"), math.nan)
        rt_ms = _float(row.get("reaction_time_ms"), math.nan)
        hit = _truthy(row.get("response_detected")) and math.isfinite(rt_ms)
        trial_uid = f"legacy-{participant}-p{part_number}-b{block_number:02d}-t{trial_number:03d}"
        trial_start = base_unix + (index * 8.0)
        tactile_onset = trial_start + 4.0 + ((soa_ms if math.isfinite(soa_ms) else 0.0) / 1000.0)
        common = {
            "participant_id": participant,
            "part_number": part_number,
            "block_number": block_number,
            "block_label": f"Part {part_number} Block {block_number:02d}",
            "trial_number": trial_number,
            "trial_uid": trial_uid,
            "trial_type": trial_type,
            "family": _clean(row.get("SOA_type")),
            "row_label": _clean(row.get("phase")),
            "soa_ms": "" if not math.isfinite(soa_ms) else int(round(soa_ms)),
            "noise_type": _clean(row.get("noise_type")),
            "respiratory_phase": _clean(row.get("phase")),
            "condition": "",
            "data_source": "legacy_import",
            "legacy_trial_reconstruction_status": _clean(row.get("trial_reconstruction_status")),
            "primary_analysis_included": True,
            "timestamp_quality": "legacy_import_no_runner_clock",
        }
        add_event("trial_start", trial_start, common)
        if trial_type in {"Audio-Tactile", "Baseline"}:
            add_event("tactile_onset", tactile_onset, {**common, "stimulus_modality": "audio+tactile" if trial_type == "Audio-Tactile" else "tactile"})
            click_event_id = ""
            click_unix_time: float | str = ""
            if hit:
                click_time = tactile_onset + (rt_ms / 1000.0)
                click_event_id = add_event(
                    "mouse_click",
                    click_time,
                    {
                        "participant_id": participant,
                        "part_number": part_number,
                        "block_number": block_number,
                        "trial_uid": trial_uid,
                        "x": "",
                        "y": "",
                        "in_target": True,
                        "during_playback": True,
                        "data_source": "legacy_import",
                        "timestamp_quality": "legacy_import_no_runner_clock",
                    },
                )
                click_unix_time = click_time
            response_rows.append(
                {
                    **common,
                    "stimulus_modality": "audio+tactile" if trial_type == "Audio-Tactile" else "tactile",
                    "is_topup": False,
                    "topup_role": "",
                    "source_trial_uid": "",
                    "topup_attempt_number": "",
                    "tactile_unix_time": tactile_onset,
                    "hit": hit,
                    "click_unix_time": click_unix_time,
                    "rt_ms": "" if not hit else rt_ms,
                    "click_x": "",
                    "click_y": "",
                    "click_event_id": click_event_id,
                }
            )
        elif trial_type == "Catch":
            add_event("looming_onset", trial_start + 4.0, {**common, "stimulus_modality": "audio"})
        add_event("trial_end", trial_start + 8.0, common)

    add_event(
        "session_end",
        base_unix + ((len(rows) + 1) * 8.0),
        {
            "participant_id": participant,
            "completed": True,
            "interrupted": False,
            "data_source": "legacy_import",
            "provenance_note": "Legacy Study 5 CSV import for runner stress testing; not runner-native acquisition.",
        },
    )
    return response_rows, events


def _write_events_csv(path: Path, rows: list[dict[str, Any]], *, participant: str, session_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["event_id", "event_type", "unix_time", "monotonic_time", "payload_json"])
        writer.writeheader()
        for row in rows:
            payload = {key: value for key, value in row.items() if key not in {"event_id", "event_type", "unix_time", "monotonic_time"}}
            payload.setdefault("participant_id", participant)
            payload.setdefault("session_id", session_id)
            writer.writerow(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "unix_time": f"{float(row['unix_time']):.9f}",
                    "monotonic_time": f"{float(row['monotonic_time']):.9f}",
                    "payload_json": json.dumps(payload, sort_keys=True, ensure_ascii=False),
                }
            )


def _write_metadata(package: Any, source_csv: Path, source_hash: str, redacted_source: Path, source_rows: int, tactile_rows: int) -> None:
    payload = {
        "schema": "pps-legacy-study5-import.v1",
        "participant_id": package.participant_id,
        "session_id": package.session_id,
        "session_dir": str(package.session_dir),
        "session_manifest": str(package.manifest_path),
        "source_sha256": source_hash,
        "source_size_bytes": source_csv.stat().st_size,
        "redacted_cleaned_csv": str(redacted_source),
        "source_row_count": source_rows,
        "tactile_response_row_count": tactile_rows,
        "imported_at_unix": time.time(),
        "provenance_note": "Legacy cleaned Study 5 CSV import for runner stress testing; not runner-native acquisition.",
    }
    (package.session_dir / "legacy_import_manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_timing_qc(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "mouse_event_id",
                "response_marker_event_id",
                "mouse_unix_time",
                "response_marker_unix_time",
                "mouse_monotonic_time",
                "response_marker_monotonic_time",
                "marker_minus_mouse_ms",
                "delay_clock",
                "marker_channel",
                "marker_gain",
                "block_number",
                "block_label",
            ],
        )
        writer.writeheader()


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "nan" else text


def _int(value: Any, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none", "nan"}


if __name__ == "__main__":
    raise SystemExit(main())
