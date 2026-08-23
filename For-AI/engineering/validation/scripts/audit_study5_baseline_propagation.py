#!/usr/bin/env python
"""Audit Study 5 baseline/no-looming propagation through generated artifacts.

This gate is deliberately concrete: it checks the committed Study 5 preload,
the materialized dashboard profile, optional prepared participant packages, and
the actual WAV samples referenced by the block CSVs. Study 5 baseline trials are
not silent trials. They must keep the first 4 s inhale/exhale instruction audio,
silence only the looming interval on auditory channels 1-2, and keep tactile
output on channel 3.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable

import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA = "pps-study5-baseline-propagation-audit.v1"
PROFILE_ID = "study5_box_breathing_pps"
EXPECTED_SOURCE_LABELS = ["Pink frontal", "White frontal"]
EXPECTED_SOURCE_NOISE_TYPES = ["pink", "white"]
EXPECTED_BLOCK_COUNTS = {"audio_tactile": 20, "baseline": 10, "catch": 4}
EXPECTED_POOL_COUNTS = {"audio_tactile": 120, "baseline": 60, "catch": 24}
EXPECTED_SEGMENT3_COUNTS = {"audio_tactile": 20, "baseline": 20, "catch": 4}
EXPECTED_SESSION_COUNTS = {"audio_tactile": 240, "baseline": 120, "catch": 48}
DEFAULT_PROFILE_DIR = (
    REPO_ROOT
    / "local_data"
    / "dashboard_projects"
    / "0_study_project_registry"
    / f"profile_{PROFILE_ID}"
)
ACTIVE_PEAK_MIN = 1e-3
TACTILE_PEAK_MIN = 1e-3
SILENCE_PEAK_MAX = 1e-4


@dataclass
class Criterion:
    section: str
    name: str
    passed: bool
    detail: str = ""
    required: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "section": self.section,
            "name": self.name,
            "passed": bool(self.passed),
            "required": bool(self.required),
            "detail": self.detail,
        }
        if self.evidence:
            payload["evidence"] = _json_ready(self.evidence)
        return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Study 5 baseline no-looming propagation.")
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--profile-dir", type=Path, default=None)
    parser.add_argument("--session-manifest", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--skip-wav-checks",
        action="store_true",
        help="Check manifests/CSVs only. Intended for metadata-only debugging, not acceptance.",
    )
    return parser


def run_audit(
    *,
    project_root: Path = REPO_ROOT,
    profile_dir: Path | None = None,
    session_manifest: Path | None = None,
    output_dir: Path | None = None,
    skip_wav_checks: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    profile = Path(profile_dir).resolve() if profile_dir is not None else DEFAULT_PROFILE_DIR.resolve()
    out = output_dir or (
        root
        / "artifacts"
        / "validation_runs"
        / f"study5_baseline_propagation_{time.strftime('%Y%m%d_%H%M%S')}"
    )
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    criteria: list[Criterion] = []
    _audit_preload_truth(root, criteria)
    _audit_materialized_profile(profile, criteria, skip_wav_checks=skip_wav_checks)
    session_summary: dict[str, Any] | None = None
    if session_manifest is not None:
        session_summary = _audit_prepared_session(
            Path(session_manifest).resolve(),
            criteria,
            skip_wav_checks=skip_wav_checks,
        )

    required = [item for item in criteria if item.required]
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "project_root": str(root),
        "profile_id": PROFILE_ID,
        "profile_dir": str(profile),
        "session_manifest": str(session_manifest.resolve()) if session_manifest is not None else "",
        "skip_wav_checks": bool(skip_wav_checks),
        "passed": all(item.passed for item in required),
        "required_count": len(required),
        "required_passed_count": sum(1 for item in required if item.passed),
        "criteria": [item.as_dict() for item in criteria],
        "sections": _section_summaries(criteria),
        "prepared_session": session_summary or {},
        "output_dir": str(out),
        "report_json": str(out / "study5_baseline_propagation_audit.json"),
        "report_md": str(out / "study5_baseline_propagation_audit.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _audit_preload_truth(root: Path, criteria: list[Criterion]) -> None:
    preload = root / "assets" / "preloads" / PROFILE_ID
    profile_metadata = _read_json(preload / "01_profile" / "profile_metadata.json")
    stimulus_sources = _read_json(preload / "02_looming_stimuli" / "stimulus_sources.json")
    baseline_strategy = _read_json(preload / "03_baseline_strategy" / "baseline_strategy.json")
    trial_design = _read_json(preload / "04_trial_designer" / "trial_design.json")
    run_defaults = _read_json(preload / "05_run_setup" / "run_defaults.json")

    title = str(profile_metadata.get("title") or "")
    title_lower = title.lower()
    criteria.append(
        Criterion(
            "preload_truth",
            "profile_id_and_title",
            profile_metadata.get("template_id") == PROFILE_ID
            and all(token in title_lower for token in ("study 5", "white", "pink")),
            "Committed preload must be the canonical Study 5 white/pink profile.",
            evidence={"template_id": profile_metadata.get("template_id"), "title": title},
        )
    )

    source_labels = _labels_from_sources(stimulus_sources)
    source_noise_types = [
        str(item.get("noise_type") or item.get("tone_type") or "").lower()
        for item in _source_items(stimulus_sources)
    ]
    criteria.append(
        Criterion(
            "preload_truth",
            "source_pool_exact",
            source_labels == EXPECTED_SOURCE_LABELS and source_noise_types == EXPECTED_SOURCE_NOISE_TYPES,
            "Study 5 must use exactly Pink frontal and White frontal, in that order.",
            evidence={"labels": source_labels, "noise_types": source_noise_types},
        )
    )

    clips = trial_design.get("custom_clip_assets")
    clips = clips if isinstance(clips, list) else []
    clip_paths = [str(item.get("path") or "") for item in clips if isinstance(item, dict)]
    clip_labels = [str(item.get("label") or "") for item in clips if isinstance(item, dict)]
    criteria.append(
        Criterion(
            "preload_truth",
            "original_study5_instruction_clips",
            clip_labels == ["Inhale instruction", "Exhale instruction"]
            and all("assets/breathing/original_study5/" in path.replace("\\", "/") for path in clip_paths),
            "The fixed inhale/exhale clips must be the original Study 5 assets.",
            evidence={"labels": clip_labels, "paths": clip_paths},
        )
    )
    criteria.append(
        Criterion(
            "preload_truth",
            "baseline_strategy_tactile_only_full_soa",
            baseline_strategy.get("template_id") == PROFILE_ID
            and baseline_strategy.get("baseline_strategy") == "tactile_only"
            and bool(baseline_strategy.get("include_baseline_trials")) is True
            and float(baseline_strategy.get("baseline_trial_percentage") or 0.0) == 0.0,
            "Baseline generation must use tactile-only files and derive timing from the full SOA list.",
            evidence=baseline_strategy,
        )
    )
    instruction_slots = (run_defaults.get("instruction_profile") or {}).get("slots") or []
    slot_paths = [str(item.get("path") or "") for item in instruction_slots if isinstance(item, dict)]
    criteria.append(
        Criterion(
            "preload_truth",
            "run_instructions_original_study5",
            bool(slot_paths) and all(path.startswith("assets/breathing/original_study5/") for path in slot_paths),
            "Run-level instruction map must point at original Study 5 instruction audio.",
            evidence={"slot_paths": slot_paths},
        )
    )


def _audit_materialized_profile(profile_dir: Path, criteria: list[Criterion], *, skip_wav_checks: bool) -> None:
    criteria.append(
        Criterion(
            "materialized_profile",
            "profile_dir_exists",
            _is_dir(profile_dir),
            "The local/dashboard materialized Study 5 profile must exist.",
            evidence={"profile_dir": str(profile_dir)},
        )
    )
    if not _is_dir(profile_dir):
        return

    study_manifest = _read_json(profile_dir / "0_profile" / "study_manifest.json")
    active_design = _read_json(profile_dir / "0_profile" / "active_design.json")
    study = study_manifest.get("study") if isinstance(study_manifest.get("study"), dict) else {}
    title = str(study.get("title") or active_design.get("name") or "")
    criteria.append(
        Criterion(
            "materialized_profile",
            "materialized_profile_identity",
            study.get("profile_id") == PROFILE_ID
            and all(token in title.lower() for token in ("study 5", "white", "pink")),
            "Materialized profile identity must match the committed Study 5 profile.",
            evidence={"profile_id": study.get("profile_id"), "title": title},
        )
    )
    _audit_no_stale_baseline_stems(profile_dir, criteria, section="materialized_profile")
    _audit_segment3(profile_dir, criteria, skip_wav_checks=skip_wav_checks)
    _audit_segment4(profile_dir, criteria)
    _audit_segment5(profile_dir, criteria)


def _audit_segment3(profile_dir: Path, criteria: list[Criterion], *, skip_wav_checks: bool) -> None:
    manifest_path = profile_dir / "3_tactile_and_baseline_trials" / "baseline_tactile_trial_files_manifest.json"
    manifest = _read_json(manifest_path)
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    counts = _family_counts(files)
    criteria.append(
        Criterion(
            "segment3",
            "segment3_counts",
            counts == EXPECTED_SEGMENT3_COUNTS,
            "Segment 3 must contain 20 audio-tactile, 20 baseline, and 4 catch WAVs.",
            evidence={"manifest": str(manifest_path), "counts": counts},
        )
    )
    baseline_rows = [row for row in files if _family(row) == "baseline"]
    stale = _stale_baseline_examples(baseline_rows)
    criteria.append(
        Criterion(
            "segment3",
            "baseline_files_use_no_looming_stem",
            not stale
            and len(baseline_rows) == EXPECTED_SEGMENT3_COUNTS["baseline"]
            and all("baseline_no_looming" in _row_path(row).name for row in baseline_rows),
            "Segment 3 baseline stems must say baseline_no_looming and never baseline_silent.",
            evidence={"stale_examples": stale[:10], "baseline_count": len(baseline_rows)},
        )
    )
    if skip_wav_checks:
        criteria.append(Criterion("segment3", "segment3_wav_behavior_skipped", True, "WAV sample checks skipped.", required=False))
        return
    source_results = []
    for row in files:
        if _family(row) not in {"audio_tactile", "baseline", "catch"}:
            continue
        result = _audit_source_wav(row)
        source_results.append(result)
    failures = [item for item in source_results if not item.get("passed")]
    criteria.append(
        Criterion(
            "segment3",
            "source_wav_signal_behavior",
            not failures and bool(source_results),
            "Segment 3 WAV samples must match family-specific Study 5 signal behavior.",
            evidence={
                "checked": len(source_results),
                "failure_count": len(failures),
                "failure_examples": failures[:8],
            },
        )
    )


def _audit_segment4(profile_dir: Path, criteria: list[Criterion]) -> None:
    csv_path = profile_dir / "4_trial_repetition_pool" / "trial_repetition_pool.csv"
    rows = _read_csv(csv_path)
    counts = _family_counts(rows)
    criteria.append(
        Criterion(
            "segment4",
            "segment4_counts",
            len(rows) == 204 and counts == EXPECTED_POOL_COUNTS,
            "Segment 4 must be 204 rows: 120 audio-tactile, 60 baseline, 24 catch.",
            evidence={"csv": str(csv_path), "row_count": len(rows), "counts": counts},
        )
    )
    stale = _stale_baseline_examples(rows)
    criteria.append(
        Criterion(
            "segment4",
            "segment4_baselines_reference_no_looming",
            not stale,
            "Segment 4 baseline rows must not reference stale baseline_silent files.",
            evidence={"stale_examples": stale[:10]},
        )
    )


def _audit_segment5(profile_dir: Path, criteria: list[Criterion]) -> None:
    block_dir = profile_dir / "5_block_csv_preview"
    block_csvs = _segment5_block_csvs(block_dir)
    criteria.append(
        Criterion(
            "segment5",
            "six_final_blocks",
            len(block_csvs) == 6,
            "Segment 5 must contain six final 34-trial block CSVs.",
            evidence={"block_dir": str(block_dir), "block_csvs": [str(path) for path in block_csvs]},
        )
    )
    block_results = []
    for path in block_csvs:
        rows = _rows_sorted(_read_csv(path))
        block_results.append(_audit_block_rows(rows, label=path.name, expect_block_counts=True))
    failures = [item for item in block_results if not item.get("passed")]
    criteria.append(
        Criterion(
            "segment5",
            "block_counts_and_row_cyclicity",
            not failures and len(block_results) == 6,
            "Every Segment 5 block must be 34 rows, 20/10/4 family split, 17/17 inhale/exhale, and row-alternating.",
            evidence={"blocks": block_results, "failure_count": len(failures)},
        )
    )
    stale = []
    for path in block_csvs:
        stale.extend(_stale_baseline_examples(_read_csv(path), prefix=path.name))
    criteria.append(
        Criterion(
            "segment5",
            "block_baselines_reference_no_looming",
            not stale,
            "Segment 5 blocks must not reference stale baseline_silent files.",
            evidence={"stale_examples": stale[:10]},
        )
    )


def _segment5_block_csvs(block_dir: Path) -> list[Path]:
    manifest = _read_json(block_dir / "block_csv_preview_manifest.json")
    paths: list[Path] = []
    for block in manifest.get("blocks", []) if isinstance(manifest.get("blocks"), list) else []:
        path = _resolve_path(block.get("csv_path"), base=block_dir)
        if path.name.startswith("block_") and path.name.endswith("_final.csv") and _path_exists(path):
            paths.append(path)
    if paths:
        return sorted(dict.fromkeys(paths), key=lambda path: path.name)
    if not _is_dir(block_dir):
        return []
    try:
        names = os.listdir(_filesystem_path(block_dir))
    except OSError:
        return []
    return sorted(
        [
            block_dir / name
            for name in names
            if name.startswith("block_") and name.endswith("_final.csv") and _path_exists(block_dir / name)
        ],
        key=lambda path: path.name,
    )


def _audit_prepared_session(session_manifest: Path, criteria: list[Criterion], *, skip_wav_checks: bool) -> dict[str, Any]:
    manifest = _read_json(session_manifest)
    blocks = manifest.get("blocks") if isinstance(manifest.get("blocks"), list) else []
    criteria.append(
        Criterion(
            "prepared_session",
            "session_manifest_exists",
            _path_exists(session_manifest) and bool(manifest),
            "Prepared participant session manifest must be readable.",
            evidence={"session_manifest": str(session_manifest), "block_count": len(blocks)},
        )
    )
    if not manifest:
        return {"session_manifest": str(session_manifest), "blocks": []}

    block_results = []
    all_rows: list[dict[str, Any]] = []
    for block in blocks:
        csv_path = _resolve_path(block.get("manifest_path") or block.get("csv_path"), base=session_manifest.parent)
        wav_path = _resolve_path(block.get("wav_path"), base=session_manifest.parent)
        rows = _rows_sorted(_read_csv(csv_path))
        all_rows.extend(rows)
        result = _audit_block_rows(
            rows,
            label=str(block.get("label") or csv_path.name),
            expect_block_counts=True,
        )
        result.update({"csv_path": str(csv_path), "wav_path": str(wav_path)})
        block_results.append(result)
    block_failures = [item for item in block_results if not item.get("passed")]
    session_counts = _family_counts(all_rows)
    criteria.append(
        Criterion(
            "prepared_session",
            "prepared_block_csv_contract",
            len(blocks) == 12
            and len(all_rows) == 408
            and session_counts == EXPECTED_SESSION_COUNTS
            and not block_failures,
            "Prepared participant package must contain 12 standard 34-trial blocks with the Study 5 240/120/48 split.",
            evidence={
                "block_count": len(blocks),
                "row_count": len(all_rows),
                "counts": session_counts,
                "block_failures": block_failures[:8],
            },
        )
    )
    stale = _stale_baseline_examples(all_rows)
    criteria.append(
        Criterion(
            "prepared_session",
            "prepared_csv_baselines_reference_no_looming",
            not stale,
            "Prepared block CSVs must not reference stale baseline_silent files.",
            evidence={"stale_examples": stale[:10]},
        )
    )
    wav_results: list[dict[str, Any]] = []
    if skip_wav_checks:
        criteria.append(
            Criterion("prepared_session", "prepared_block_wav_behavior_skipped", True, "Prepared WAV checks skipped.", required=False)
        )
    else:
        for block in blocks:
            csv_path = _resolve_path(block.get("manifest_path") or block.get("csv_path"), base=session_manifest.parent)
            wav_path = _resolve_path(block.get("wav_path"), base=session_manifest.parent)
            wav_results.append(_audit_prepared_block_wav(csv_path=csv_path, wav_path=wav_path))
        wav_failures = [item for item in wav_results if not item.get("passed")]
        criteria.append(
            Criterion(
                "prepared_session",
                "prepared_block_wav_signal_behavior",
                not wav_failures and bool(wav_results),
                "Prepared block WAV samples must preserve baseline instruction audio, no-looming silence, tactile cues, and catch no-tactile behavior.",
                evidence={
                    "checked_blocks": len(wav_results),
                    "failure_count": len(wav_failures),
                    "failure_examples": wav_failures[:6],
                },
            )
        )
    return {
        "session_manifest": str(session_manifest),
        "block_count": len(blocks),
        "row_count": len(all_rows),
        "counts": session_counts,
        "block_results": block_results,
        "wav_results": wav_results,
    }


def _audit_no_stale_baseline_stems(profile_dir: Path, criteria: list[Criterion], *, section: str) -> None:
    stale_paths = _stale_baseline_artifact_paths(profile_dir)
    criteria.append(
        Criterion(
            section,
            "no_baseline_silent_artifacts",
            not stale_paths,
            "No materialized Study 5 artifact may use the old baseline_silent stem.",
            evidence={"examples": stale_paths[:20], "count": len(stale_paths)},
        )
    )


def _stale_baseline_artifact_paths(profile_dir: Path) -> list[str]:
    if not _is_dir(profile_dir):
        return []
    stale: list[str] = []
    try:
        walker = os.walk(_filesystem_path(profile_dir))
        for root_text, _dir_names, file_names in walker:
            for name in file_names:
                if "baseline_silent" in name.lower():
                    stale.append(str(Path(root_text) / name))
    except OSError:
        return stale
    return sorted(stale)


def _audit_block_rows(
    rows: list[dict[str, Any]],
    *,
    label: str,
    expect_block_counts: bool,
) -> dict[str, Any]:
    phases = [_phase(row) for row in rows]
    counts = _family_counts(rows)
    phase_counts = Counter(phases)
    stale = _stale_baseline_examples(rows)
    checks = {
        "trial_count": len(rows) == 34 if expect_block_counts else bool(rows),
        "family_counts": counts == EXPECTED_BLOCK_COUNTS if expect_block_counts else bool(counts),
        "phase_counts": dict(phase_counts) == {"inhale": 17, "exhale": 17} if expect_block_counts else True,
        "phase_alternation": _alternates_inhale_exhale(phases),
        "no_stale_baseline_silent": not stale,
        "baseline_no_looming_stems": all(
            "baseline_no_looming" in _row_path(row).name
            for row in rows
            if _family(row) == "baseline"
        ),
    }
    return {
        "label": label,
        "passed": all(checks.values()),
        "checks": checks,
        "trial_count": len(rows),
        "family_counts": counts,
        "phase_counts": dict(phase_counts),
        "phase_sequence_head": phases[:12],
        "stale_examples": stale[:8],
    }


def _audit_source_wav(row: dict[str, Any]) -> dict[str, Any]:
    family = _family(row)
    path = _row_path(row)
    base = {"family": family, "path": str(path), "source_file_name": _row_name(row)}
    if not _path_exists(path):
        return {**base, "passed": False, "reason": "missing_wav"}
    try:
        data, sr = sf.read(_filesystem_path(path), dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001 - validation report should retain bad files.
        return {**base, "passed": False, "reason": f"read_failed: {exc}"}
    looming_s = _as_float(row.get("looming_segment_onset_s"), 4.0)
    if family == "baseline":
        metrics = baseline_no_looming_metrics(data, sr, looming_offset_s=looming_s)
    elif family == "catch":
        metrics = catch_audio_only_metrics(data, sr, looming_offset_s=looming_s)
    else:
        metrics = audio_tactile_metrics(data, sr, looming_offset_s=looming_s)
    return {**base, **metrics}


def _audit_prepared_block_wav(*, csv_path: Path, wav_path: Path) -> dict[str, Any]:
    rows = _rows_sorted(_read_csv(csv_path))
    result: dict[str, Any] = {
        "csv_path": str(csv_path),
        "wav_path": str(wav_path),
        "passed": False,
        "trial_count": len(rows),
    }
    if not _path_exists(csv_path):
        return {**result, "reason": "missing_block_csv"}
    if not _path_exists(wav_path):
        return {**result, "reason": "missing_block_wav"}
    try:
        data, sr = sf.read(_filesystem_path(wav_path), dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001
        return {**result, "reason": f"read_failed: {exc}"}
    failures = []
    checked = 0
    for row in rows:
        family = _family(row)
        start = _as_int(row.get("Trial_Start_Sample") or row.get("trial_start_sample"), None)
        end = _as_int(row.get("Trial_End_Sample") or row.get("trial_end_sample"), None)
        if start is None or end is None:
            failures.append({"trial": _trial_label(row), "family": family, "reason": "missing_trial_sample_bounds"})
            continue
        if family == "baseline":
            metrics = baseline_no_looming_metrics(data, sr, start_sample=start, end_sample=end, looming_offset_s=4.0)
        elif family == "catch":
            metrics = catch_audio_only_metrics(data, sr, start_sample=start, end_sample=end, looming_offset_s=4.0)
        elif family == "audio_tactile":
            metrics = audio_tactile_metrics(data, sr, start_sample=start, end_sample=end, looming_offset_s=4.0)
        else:
            continue
        checked += 1
        if not metrics["passed"]:
            failures.append(
                {
                    "trial": _trial_label(row),
                    "family": family,
                    "source_file_name": _row_name(row),
                    "metrics": {key: value for key, value in metrics.items() if key != "passed"},
                }
            )
    return {
        **result,
        "passed": not failures and checked == len(rows),
        "sample_rate": sr,
        "channels": int(data.shape[1]),
        "checked_trials": checked,
        "failure_count": len(failures),
        "failure_examples": failures[:8],
    }


def baseline_no_looming_metrics(
    data: np.ndarray,
    sample_rate: int,
    *,
    start_sample: int = 0,
    end_sample: int | None = None,
    looming_offset_s: float = 4.0,
) -> dict[str, Any]:
    data = _window(data, start_sample, end_sample)
    boundary = _clamp_index(round(float(looming_offset_s) * sample_rate), data.shape[0])
    pre_audio = data[:boundary, :2] if data.shape[1] >= 2 else data[:0, :0]
    post_audio = data[boundary:, :2] if data.shape[1] >= 2 else data[:0, :0]
    tactile = data[:, 2] if data.shape[1] >= 3 else data[:0, 0]
    pre_peak = _peak(pre_audio)
    post_peak = _peak(post_audio)
    tactile_peak = _peak(tactile)
    passed = (
        data.shape[1] >= 3
        and boundary > 0
        and pre_peak >= ACTIVE_PEAK_MIN
        and post_peak <= SILENCE_PEAK_MAX
        and tactile_peak >= TACTILE_PEAK_MIN
    )
    return {
        "passed": bool(passed),
        "channels": int(data.shape[1]),
        "pre_instruction_audio_peak": pre_peak,
        "looming_interval_audio_peak": post_peak,
        "tactile_peak": tactile_peak,
        "looming_offset_s": float(looming_offset_s),
    }


def catch_audio_only_metrics(
    data: np.ndarray,
    sample_rate: int,
    *,
    start_sample: int = 0,
    end_sample: int | None = None,
    looming_offset_s: float = 4.0,
) -> dict[str, Any]:
    data = _window(data, start_sample, end_sample)
    boundary = _clamp_index(round(float(looming_offset_s) * sample_rate), data.shape[0])
    pre_peak = _peak(data[:boundary, :2]) if data.shape[1] >= 2 else 0.0
    post_peak = _peak(data[boundary:, :2]) if data.shape[1] >= 2 else 0.0
    tactile_peak = _peak(data[:, 2]) if data.shape[1] >= 3 else 0.0
    passed = data.shape[1] >= 2 and pre_peak >= ACTIVE_PEAK_MIN and post_peak >= ACTIVE_PEAK_MIN and tactile_peak <= SILENCE_PEAK_MAX
    return {
        "passed": bool(passed),
        "channels": int(data.shape[1]),
        "pre_instruction_audio_peak": pre_peak,
        "looming_interval_audio_peak": post_peak,
        "tactile_peak": tactile_peak,
        "looming_offset_s": float(looming_offset_s),
    }


def audio_tactile_metrics(
    data: np.ndarray,
    sample_rate: int,
    *,
    start_sample: int = 0,
    end_sample: int | None = None,
    looming_offset_s: float = 4.0,
) -> dict[str, Any]:
    data = _window(data, start_sample, end_sample)
    boundary = _clamp_index(round(float(looming_offset_s) * sample_rate), data.shape[0])
    pre_peak = _peak(data[:boundary, :2]) if data.shape[1] >= 2 else 0.0
    post_peak = _peak(data[boundary:, :2]) if data.shape[1] >= 2 else 0.0
    tactile_peak = _peak(data[:, 2]) if data.shape[1] >= 3 else 0.0
    passed = data.shape[1] >= 3 and pre_peak >= ACTIVE_PEAK_MIN and post_peak >= ACTIVE_PEAK_MIN and tactile_peak >= TACTILE_PEAK_MIN
    return {
        "passed": bool(passed),
        "channels": int(data.shape[1]),
        "pre_instruction_audio_peak": pre_peak,
        "looming_interval_audio_peak": post_peak,
        "tactile_peak": tactile_peak,
        "looming_offset_s": float(looming_offset_s),
    }


def _source_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("sources", "stimuli", "files", "assets"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _labels_from_sources(payload: dict[str, Any]) -> list[str]:
    return [str(item.get("label") or item.get("source_label") or "") for item in _source_items(payload)]


def _family(row: dict[str, Any]) -> str:
    value = row.get("family") or row.get("Family") or row.get("Trial_Type") or row.get("trial_type") or ""
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if "audio" in text and "tactile" in text:
        return "audio_tactile"
    if "baseline" in text:
        return "baseline"
    if "catch" in text:
        return "catch"
    return text


def _family_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        family = _family(row)
        if family:
            counts[family] += 1
    return {key: counts.get(key, 0) for key in ("audio_tactile", "baseline", "catch")}


def _phase(row: dict[str, Any]) -> str:
    for keys in (
        ("Respiratory_Phase", "respiratory_phase"),
        ("Row_Label", "row_label", "Row", "row"),
        ("sequence_labels", "Sequence_Labels"),
        ("source_file_name", "Source_File_Name"),
    ):
        text = " ".join(str(row.get(key) or "") for key in keys).lower()
        if "exhale" in text:
            return "exhale"
        if "inhale" in text:
            return "inhale"
    return ""


def _alternates_inhale_exhale(phases: list[str]) -> bool:
    if not phases or any(phase not in {"inhale", "exhale"} for phase in phases):
        return False
    return all(left != right for left, right in zip(phases, phases[1:]))


def _rows_sorted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=_row_sort_key)


def _row_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    for key in ("Trial_Number", "trial_number", "block_trial_index", "Segment5_Block_Trial_Index"):
        value = _as_int(row.get(key), None)
        if value is not None:
            return (value, "")
    return (10**9, str(row))


def _row_path(row: dict[str, Any]) -> Path:
    value = (
        row.get("file_path")
        or row.get("trial_file_path")
        or row.get("Trial_File_Path")
        or row.get("source_audio_path")
        or row.get("Source_File_Path")
        or ""
    )
    return Path(str(value))


def _row_name(row: dict[str, Any]) -> str:
    path = _row_path(row)
    if path.name:
        return path.name
    return str(row.get("source_file_name") or row.get("Source_File_Name") or "")


def _stale_baseline_examples(rows: Iterable[dict[str, Any]], *, prefix: str = "") -> list[str]:
    examples = []
    for row in rows:
        if _family(row) != "baseline":
            continue
        name = _row_name(row)
        text = " ".join(str(row.get(key) or "") for key in row.keys())
        if "baseline_silent" in name or "baseline_silent" in text:
            examples.append(f"{prefix}:{name}" if prefix else name)
    return examples


def _trial_label(row: dict[str, Any]) -> str:
    return str(row.get("Trial_UID") or row.get("trial_uid") or row.get("Trial_Number") or row.get("block_trial_index") or "")


def _window(data: np.ndarray, start_sample: int, end_sample: int | None) -> np.ndarray:
    start = max(0, int(start_sample))
    end = data.shape[0] if end_sample is None else min(data.shape[0], max(start, int(end_sample)))
    return data[start:end, :]


def _clamp_index(index: int, length: int) -> int:
    return max(0, min(int(index), int(length)))


def _peak(data: np.ndarray) -> float:
    if data.size == 0:
        return 0.0
    return float(np.max(np.abs(data)))


def _as_float(value: Any, default: float) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return float(default)


def _as_int(value: Any, default: int | None) -> int | None:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _resolve_path(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not _path_exists(path):
        return []
    with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_exists(path: str | Path) -> bool:
    try:
        return os.path.exists(_filesystem_path(path))
    except OSError:
        return False


def _is_dir(path: str | Path) -> bool:
    try:
        return os.path.isdir(_filesystem_path(path))
    except OSError:
        return False


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    failed = [item for item in report.get("criteria", []) if item.get("required", True) and not item.get("passed")]
    lines = [
        "# Study 5 Baseline Propagation Audit",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Profile dir: `{report.get('profile_dir')}`",
        f"- Session manifest: `{report.get('session_manifest')}`",
        f"- Required criteria: `{report.get('required_passed_count')}` / `{report.get('required_count')}`",
        "",
    ]
    if failed:
        lines.extend(["## Blocking Criteria", ""])
        for item in failed[:20]:
            lines.append(f"- `{item.get('section')}.{item.get('name')}`: {item.get('detail')}")
        lines.append("")
    lines.extend(["## Sections", ""])
    for section, summary in sorted((report.get("sections") or {}).items()):
        lines.append(f"- `{section}`: `{summary.get('passed')}` ({summary.get('passed_count')}/{summary.get('count')})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _section_summaries(criteria: list[Criterion]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for item in criteria:
        row = summaries.setdefault(item.section, {"count": 0, "passed_count": 0, "required_count": 0, "required_passed_count": 0})
        row["count"] += 1
        row["passed_count"] += int(bool(item.passed))
        row["required_count"] += int(bool(item.required))
        row["required_passed_count"] += int(bool(item.required and item.passed))
    for row in summaries.values():
        row["passed"] = row["required_count"] == row["required_passed_count"]
    return summaries


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_audit(
        project_root=args.project_root,
        profile_dir=args.profile_dir,
        session_manifest=args.session_manifest,
        output_dir=args.output_dir,
        skip_wav_checks=args.skip_wav_checks,
    )
    print(f"Wrote Study 5 baseline propagation audit: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
