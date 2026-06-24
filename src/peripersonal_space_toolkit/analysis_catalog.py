"""Folder-local analysis catalog and participant-pool outputs."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .analysis_review import load_analysis_review_data
from .output_layout import _filesystem_path, output_data_analytics_dir, output_runner_logs_dir
from .session_analysis import (
    QUALITY_FAIL,
    QUALITY_PASS,
    RECORDING_QUALITY_GATE_SCHEMA,
    analyze_analysis_ready_trials,
    format_analysis_summary,
    write_analysis_csvs,
)


ANALYSIS_CATALOG_SCHEMA = "pps-analysis-catalog.v1"
ANALYSIS_CATALOG_FILENAME = "analysis_catalog.v1.json"
PARTICIPANT_COMBINED_DIRNAME = "participant_combined"
PARTICIPANT_POOL_DIRNAME = "_participant_pool"
DATASET_KIND_PARTICIPANT = "participant"
DATASET_KIND_PART = "part"
DATASET_KIND_POOL = "participant_pool"


@dataclass
class AnalysisCatalog:
    output_root: Path
    path: Path
    entries: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def selectable_entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if bool(entry.get("selectable", True))]

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": ANALYSIS_CATALOG_SCHEMA,
            "output_root": str(self.output_root),
            "data_analytics_dir": str(output_data_analytics_dir(self.output_root)),
            "entries": self.entries,
            "warnings": self.warnings,
        }


def analysis_catalog_path(output_root: Path | str) -> Path:
    return output_data_analytics_dir(output_root) / ANALYSIS_CATALOG_FILENAME


def refresh_analysis_catalog(output_root: Path | str) -> AnalysisCatalog:
    root = Path(output_root).expanduser()
    catalog = AnalysisCatalog(output_root=root, path=analysis_catalog_path(root), entries=_discover_analysis_entries(root))
    _write_catalog(catalog)
    return catalog


def refresh_analysis_browser_outputs(output_root: Path | str, *, preferred_participant_id: str = "") -> AnalysisCatalog:
    """Refresh derived participant-combined and PASS-only pool artifacts."""

    root = Path(output_root).expanduser()
    analytics_root = output_data_analytics_dir(root)
    _mkdir(analytics_root)
    warnings: list[str] = []
    try:
        _refresh_split_participant_outputs(root)
    except Exception as exc:  # noqa: BLE001 - catalog refresh must not block run completion.
        warnings.append(f"Could not refresh split-participant analysis outputs: {exc}")
    try:
        participant_entries = _participant_entries_for_pool(root)
        _build_participant_pool_outputs(root, participant_entries)
    except Exception as exc:  # noqa: BLE001 - catalog refresh must not block run completion.
        warnings.append(f"Could not refresh participant-pool analysis outputs: {exc}")
    catalog = AnalysisCatalog(output_root=root, path=analysis_catalog_path(root), entries=_discover_analysis_entries(root), warnings=warnings)
    _write_catalog(catalog)
    return catalog


def load_analysis_dataset(entry: dict[str, Any]):
    data = load_analysis_review_data(
        entry.get("outputs", {}),
        session_dir=entry.get("analysis_dir") or None,
        summary_text=_read_text(Path(entry.get("summary_text_path") or "")),
        dataset_metadata=entry,
    )
    return data


def selected_dataset_id_for_participant(catalog: AnalysisCatalog, participant_id: str) -> str:
    participant = str(participant_id or "").strip()
    for entry in catalog.selectable_entries:
        if entry.get("dataset_kind") == DATASET_KIND_PARTICIPANT and str(entry.get("participant_id") or "").strip() == participant:
            return str(entry.get("dataset_id") or "")
    return ""


def _refresh_split_participant_outputs(output_root: Path) -> None:
    part_entries = [entry for entry in _discover_analysis_entries(output_root, include_derived=False) if entry.get("dataset_kind") == DATASET_KIND_PART]
    by_group: dict[str, list[dict[str, Any]]] = {}
    for entry in part_entries:
        group = str(entry.get("session_group_id") or "").strip()
        if group:
            by_group.setdefault(group, []).append(entry)
    for group, entries in by_group.items():
        manifest = output_runner_logs_dir(output_root) / group / "session_group_manifest.json"
        payload = _read_json(manifest)
        parts = payload.get("parts", []) if isinstance(payload, dict) else []
        if not parts or not all(bool(part.get("completed")) for part in parts if isinstance(part, dict)):
            continue
        expected_names = {str(part.get("part_folder_name") or "").strip() for part in parts if isinstance(part, dict)}
        if expected_names:
            entries = [entry for entry in entries if Path(str(entry.get("analysis_dir") or "")).name in expected_names]
            if {Path(str(entry.get("analysis_dir") or "")).name for entry in entries} != expected_names:
                continue
        rows: list[dict[str, Any]] = []
        part_quality = []
        for entry in sorted(entries, key=lambda item: int(item.get("part_number") or 0)):
            rows.extend(_read_csv_rows(Path(str((entry.get("outputs") or {}).get("analysis_ready_trials") or ""))))
            part_quality.append(dict(entry.get("recording_quality_gate") or {}))
        if not rows:
            continue
        result = analyze_analysis_ready_trials(rows)
        result.recording_quality_gate = _merged_participant_quality_gate(result.recording_quality_gate, part_quality)
        analysis_dir = output_data_analytics_dir(output_root) / group / PARTICIPANT_COMBINED_DIRNAME
        stem = f"{group}_participant_combined"
        outputs = write_analysis_csvs(result, analysis_dir, stem)
        _write_text(analysis_dir / "analysis_summary.txt", format_analysis_summary(result) + "\n")
        outputs["analysis_summary"] = analysis_dir / "analysis_summary.txt"


def _participant_entries_for_pool(output_root: Path) -> list[dict[str, Any]]:
    entries = [
        entry
        for entry in _discover_analysis_entries(output_root)
        if entry.get("dataset_kind") == DATASET_KIND_PARTICIPANT
        and str(entry.get("quality_status") or "").upper() == QUALITY_PASS
    ]
    return sorted(entries, key=lambda entry: str(entry.get("participant_id") or ""))


def _build_participant_pool_outputs(output_root: Path, participant_entries: list[dict[str, Any]]) -> dict[str, Path]:
    completed_participants = [
        entry
        for entry in _discover_analysis_entries(output_root)
        if entry.get("dataset_kind") == DATASET_KIND_PARTICIPANT
    ]
    excluded_count = max(0, len(completed_participants) - len(participant_entries))
    if not participant_entries:
        return {}
    rows = _participant_balanced_rows(participant_entries)
    if not rows:
        return {}
    result = analyze_analysis_ready_trials(rows)
    _apply_group_model_support(result, participant_entries)
    result.recording_quality_gate = {
        "schema": RECORDING_QUALITY_GATE_SCHEMA,
        "status": QUALITY_PASS,
        "primary_reason": f"Participant pool includes {len(participant_entries)} PASS participant dataset(s); {excluded_count} failed dataset(s) excluded.",
        "failures": [],
        "warnings": [],
        "metrics": {
            "included_participants": len(participant_entries),
            "excluded_participants": excluded_count,
            "pool_inclusion_policy": "PASS_only",
        },
    }
    analysis_dir = output_data_analytics_dir(output_root) / PARTICIPANT_POOL_DIRNAME
    outputs = write_analysis_csvs(result, analysis_dir, "participant_pool")
    _write_text(analysis_dir / "analysis_summary.txt", format_analysis_summary(result) + "\n")
    outputs["analysis_summary"] = analysis_dir / "analysis_summary.txt"
    return outputs


def _participant_balanced_rows(participant_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    synthetic: list[dict[str, Any]] = []
    for entry in participant_entries:
        participant = str(entry.get("participant_id") or "").strip()
        rows = _read_csv_rows(Path(str((entry.get("outputs") or {}).get("analysis_ready_trials") or "")))
        audio_groups: dict[tuple[Any, ...], list[float]] = {}
        baseline_groups: dict[tuple[Any, ...], list[tuple[float, int]]] = {}
        for row in rows:
            trial_type = str(row.get("trial_type") or row.get("Trial_Type") or "").strip()
            if trial_type not in {"Audio-Tactile", "Baseline"}:
                continue
            rt = _as_float(row.get("rt_ms") or row.get("RT_ms"), math.nan)
            if not math.isfinite(rt):
                continue
            part_number = _as_int(row.get("part_number") or row.get("Part_Number"), "")
            phase = str(row.get("respiratory_phase") or row.get("Respiratory_Phase") or "").strip()
            soa = _as_int(row.get("soa_ms") or row.get("SOA_ms"), None)
            if trial_type == "Audio-Tactile" and soa is not None:
                audio_groups.setdefault((participant, part_number, phase, int(soa)), []).append(rt)
            elif trial_type == "Baseline":
                baseline_groups.setdefault((participant, part_number, phase), []).append((rt, int(soa or 0)))
        for (source_participant, part_number, phase, soa), values in sorted(audio_groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
            synthetic.append(
                {
                    "participant_id": source_participant,
                    "trial_uid": f"pool_{source_participant}_{part_number}_{phase}_{soa}_audio",
                    "trial_type": "Audio-Tactile",
                    "part_number": part_number,
                    "respiratory_phase": phase,
                    "condition": "",
                    "noise_type": "",
                    "soa_ms": soa,
                    "rt_ms": statistics.mean(values),
                    "hit": True,
                    "primary_analysis_included": True,
                    "pool_source_trial_count": len(values),
                }
            )
        for (source_participant, part_number, phase), samples in sorted(baseline_groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
            values = [value for value, _soa in samples]
            source_soas = [soa for _value, soa in samples]
            synthetic.append(
                {
                    "participant_id": source_participant,
                    "trial_uid": f"pool_{source_participant}_{part_number}_{phase}_baseline",
                    "trial_type": "Baseline",
                    "part_number": part_number,
                    "respiratory_phase": phase,
                    "condition": "",
                    "noise_type": "",
                    "soa_ms": min(source_soas) if source_soas else 0,
                    "rt_ms": statistics.mean(values),
                    "hit": True,
                    "primary_analysis_included": True,
                    "pool_source_trial_count": len(values),
                    "pool_baseline_source_soas_ms": ";".join(str(soa) for soa in sorted(set(source_soas))),
                }
            )
    return synthetic


def _apply_group_model_support(result: Any, participant_entries: list[dict[str, Any]]) -> None:
    summary = dict(result.condition_lens_triage_summary or {})
    overall = summary.get("overall_model", {}) if isinstance(summary.get("overall_model"), dict) else {}
    group_winner = str(overall.get("best_model") or summary.get("default_model") or "").strip()
    group_tier = str(overall.get("evidence_tier") or "").strip()
    participant_wins: dict[str, int] = {}
    for entry in participant_entries:
        triage = _read_json(Path(str((entry.get("outputs") or {}).get("condition_lens_triage_summary") or "")))
        model = ""
        if isinstance(triage.get("overall_model"), dict):
            model = str(triage["overall_model"].get("best_model") or "").strip()
        model = model or str(triage.get("default_model") or "").strip()
        if model:
            participant_wins[model] = participant_wins.get(model, 0) + 1
    majority_model = ""
    if participant_wins:
        count, model = max((count, model) for model, count in participant_wins.items())
        if count > len(participant_entries) / 2:
            majority_model = model
    support = "supported" if group_winner and group_winner == majority_model and group_tier == "strong" else "mixed"
    model_buttons = summary.get("model_button_summaries", {})
    if isinstance(model_buttons, dict) and group_winner in model_buttons and isinstance(model_buttons[group_winner], dict):
        model_buttons[group_winner]["evidence_tier"] = "strong" if support == "supported" else "mixed"
        model_buttons[group_winner]["group_support"] = support
    summary["group_model_support"] = {
        "support": support,
        "group_winner": group_winner,
        "group_evidence_tier": group_tier,
        "participant_majority_model": majority_model,
        "participant_model_wins": participant_wins,
        "participant_count": len(participant_entries),
        "criterion": "supported only when group winner, strong group AICc tier, and participant majority agree",
    }
    summary["interpretation_note"] = (
        "Participant-pool model colors are exploratory triage cues. A group model is marked supported only when "
        "the participant-balanced group fit and the majority participant-level model winner agree."
    )
    result.condition_lens_triage_summary = summary


def _merged_participant_quality_gate(computed: dict[str, Any], part_quality: list[dict[str, Any]]) -> dict[str, Any]:
    failures = list(computed.get("failures") or [])
    part_failures = []
    for index, quality in enumerate(part_quality, start=1):
        status = str(quality.get("status") or "").strip().upper()
        if status != QUALITY_PASS:
            part_failures.append(
                {
                    "code": "split_part_quality_failed",
                    "message": f"Part {index} failed serious exclusion criteria.",
                    "evidence": str(quality.get("primary_reason") or status or "UNKNOWN"),
                }
            )
    failures.extend(part_failures)
    status = QUALITY_FAIL if failures else str(computed.get("status") or QUALITY_PASS).upper()
    return {
        **computed,
        "status": status,
        "primary_reason": (
            "At least one required split part failed serious exclusion criteria."
            if part_failures
            else computed.get("primary_reason", "No serious exclusion criteria were triggered across the complete participant dataset.")
        ),
        "failures": failures,
        "component_part_quality": part_quality,
    }


def _discover_analysis_entries(output_root: Path, *, include_derived: bool = True) -> list[dict[str, Any]]:
    analytics_root = output_data_analytics_dir(output_root)
    if not analytics_root.exists():
        return []
    entries: list[dict[str, Any]] = []
    seen_dirs: set[Path] = set()
    for analysis_ready in sorted(analytics_root.rglob("*_analysis_ready_trials.csv")):
        analysis_dir = analysis_ready.parent
        if analysis_dir in seen_dirs:
            continue
        seen_dirs.add(analysis_dir)
        if not include_derived and analysis_dir.name in {PARTICIPANT_COMBINED_DIRNAME, PARTICIPANT_POOL_DIRNAME}:
            continue
        entry = _entry_for_analysis_dir(output_root, analysis_dir)
        if entry is not None:
            entries.append(entry)
    return sorted(entries, key=_entry_sort_key)


def _entry_for_analysis_dir(output_root: Path, analysis_dir: Path) -> dict[str, Any] | None:
    outputs = _outputs_for_analysis_dir(analysis_dir)
    analysis_ready = outputs.get("analysis_ready_trials")
    if analysis_ready is None or not Path(analysis_ready).is_file():
        return None
    rows = _read_csv_rows(Path(analysis_ready), limit=8)
    quality = _read_json(Path(str(outputs.get("recording_quality_gate") or "")))
    participant_id = _first_value(rows, "participant_id", "Participant_ID")
    session_id = _session_id_from_stem(Path(analysis_ready).name)
    rel_parts = analysis_dir.relative_to(output_data_analytics_dir(output_root)).parts
    dataset_kind = DATASET_KIND_PARTICIPANT
    selectable = True
    session_group_id = ""
    part_number: int | str = ""
    if analysis_dir.name == PARTICIPANT_POOL_DIRNAME:
        dataset_kind = DATASET_KIND_POOL
        participant_id = ""
        dataset_id = "participant_pool"
        label = _pool_label(quality)
    elif analysis_dir.name == PARTICIPANT_COMBINED_DIRNAME:
        session_group_id = rel_parts[0] if rel_parts else ""
        dataset_id = f"participant:{participant_id or session_group_id}"
        label = participant_id or session_group_id
    elif analysis_dir.name.startswith("part_") and len(rel_parts) >= 2:
        dataset_kind = DATASET_KIND_PART
        selectable = False
        session_group_id = rel_parts[0]
        part_number = _part_number_from_name(analysis_dir.name)
        dataset_id = f"part:{session_id}"
        label = f"{participant_id or session_group_id} Part {part_number}"
    else:
        dataset_id = f"participant:{participant_id or session_id}"
        label = participant_id or session_id
    if dataset_kind == DATASET_KIND_POOL:
        included = int((quality.get("metrics") or {}).get("included_participants") or 0)
        excluded = int((quality.get("metrics") or {}).get("excluded_participants") or 0)
    else:
        included = 0
        excluded = 0
    return {
        "schema": ANALYSIS_CATALOG_SCHEMA,
        "dataset_id": dataset_id,
        "dataset_kind": dataset_kind,
        "dataset_label": label,
        "participant_id": participant_id,
        "session_id": session_id,
        "session_group_id": session_group_id,
        "part_number": part_number,
        "selectable": selectable,
        "pool_inclusion_policy": "PASS_only",
        "pool_included": dataset_kind == DATASET_KIND_PARTICIPANT and str(quality.get("status") or "").upper() == QUALITY_PASS,
        "pool_included_count": included,
        "pool_excluded_count": excluded,
        "quality_status": str(quality.get("status") or "").upper(),
        "quality_reason": str(quality.get("primary_reason") or ""),
        "analysis_dir": str(analysis_dir),
        "summary_text_path": str(analysis_dir / "analysis_summary.txt"),
        "outputs": {key: str(path) for key, path in outputs.items()},
        "recording_quality_gate": quality,
    }


def _outputs_for_analysis_dir(analysis_dir: Path) -> dict[str, Path]:
    patterns: dict[str, tuple[str, tuple[str, ...]]] = {
        "responses": ("*_responses.csv", ()),
        "analysis_ready_trials": ("*_analysis_ready_trials.csv", ()),
        "final_trial_outcomes": ("*_final_trial_outcomes.csv", ()),
        "summary": ("*_summary.csv", ()),
        "curves": ("*_pps_curve_points.csv", ()),
        "fits": ("*_sigmoid_fits.csv", ()),
        "model_fits": ("*_model_fits.csv", ("condition_lens_",)),
        "model_fit_comparison": ("*_model_fit_comparison.csv", ("condition_lens_",)),
        "condition_lens_curves": ("*_condition_lens_curve_points.csv", ()),
        "condition_lens_model_fits": ("*_condition_lens_model_fits.csv", ()),
        "condition_lens_model_fit_comparison": ("*_condition_lens_model_fit_comparison.csv", ()),
        "timing_qc": ("*_timing_qc.csv", ()),
    }
    outputs = {
        key: path
        for key, (pattern, excludes) in patterns.items()
        if (path := _first_glob(analysis_dir, pattern, excludes=excludes)) is not None
    }
    fixed = {
        "condition_lens_triage_summary": "condition_lens_triage_summary.json",
        "recording_quality_gate": "recording_quality_gate.v1.json",
        "data_behavior_by_scope": "data_behavior_by_scope.csv",
        "exploratory_quality_summary": "exploratory_quality_summary.json",
    }
    for key, filename in fixed.items():
        path = analysis_dir / filename
        if path.is_file():
            outputs[key] = path
    return outputs


def _write_catalog(catalog: AnalysisCatalog) -> None:
    _mkdir(catalog.path.parent)
    with open(_filesystem_path(catalog.path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(catalog.as_payload()), indent=2, sort_keys=True) + "\n")


def _read_csv_rows(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append(dict(row))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    if not path or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _write_text(path: Path, text: str) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(text)


def _mkdir(path: Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


def _first_glob(path: Path, pattern: str, *, excludes: Iterable[str] = ()) -> Path | None:
    matches = sorted(candidate for candidate in path.glob(pattern) if not any(text in candidate.name for text in excludes))
    return matches[0] if matches else None


def _first_value(rows: list[dict[str, Any]], *keys: str) -> str:
    for row in rows:
        for key in keys:
            value = str(row.get(key) or "").strip()
            if value:
                return value
    return ""


def _session_id_from_stem(filename: str) -> str:
    for suffix in (
        "_analysis_ready_trials.csv",
        "_participant_combined_analysis_ready_trials.csv",
    ):
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    return filename.replace("_analysis_ready_trials.csv", "")


def _pool_label(quality: dict[str, Any]) -> str:
    metrics = quality.get("metrics", {}) if isinstance(quality.get("metrics"), dict) else {}
    included = int(metrics.get("included_participants") or 0)
    excluded = int(metrics.get("excluded_participants") or 0)
    return f"Participant pool aggregate ({included} included, {excluded} excluded)"


def _part_number_from_name(name: str) -> int | str:
    text = str(name or "").strip().lower().replace("part_", "")
    try:
        return int(text)
    except ValueError:
        return ""


def _entry_sort_key(entry: dict[str, Any]) -> tuple[int, str, str]:
    kind = str(entry.get("dataset_kind") or "")
    rank = 0 if kind == DATASET_KIND_POOL else 1 if kind == DATASET_KIND_PARTICIPANT else 2
    return (rank, str(entry.get("participant_id") or ""), str(entry.get("dataset_label") or ""))


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _as_int(value: Any, default: Any) -> Any:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)
