"""Published-profile recreation readiness audit helpers."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .design import StimulusDesign, has_trial_strips, validate_design
from .templates import StudyTemplate


PROFILE_PARAMETERS_SCHEMA = "pps-study-profile-parameters.v1"
PROFILE_RECREATION_STATUS_SCHEMA = "pps-profile-recreation-status.v1"

STATUS_REPORTED = "reported"
STATUS_INFERRED = "inferred"
STATUS_DEFAULTED = "defaulted"
STATUS_MISSING = "missing_publication_parameter"
STATUS_UNSUPPORTED = "unsupported_toolkit_structure"

CATEGORY_GUI_RECREATABLE = "gui_recreatable"
CATEGORY_MISSING_PUBLICATION_PARAMETERS = "missing_publication_parameters"
CATEGORY_TOOLKIT_STRUCTURAL_GAP = "toolkit_structural_gap"

CATEGORY_LABELS = {
    CATEGORY_GUI_RECREATABLE: "GUI-recreatable",
    CATEGORY_MISSING_PUBLICATION_PARAMETERS: "Missing publication parameters",
    CATEGORY_TOOLKIT_STRUCTURAL_GAP: "Toolkit structural gap",
}

READY_RUNNER = "ready"
BLOCKED_MISSING = "blocked_missing_parameters"
BLOCKED_UNSUPPORTED = "blocked_unsupported_toolkit_structure"

SEGMENT_LABELS = {
    "0": "Segment 0 profile manifest and provenance",
    "1": "Segment 1 source/stimulus assets",
    "2": "Segment 2 trial rows and sequences",
    "3": "Segment 3 SOA, tactile, baseline, and catch settings",
    "4": "Segment 4 repetition pool settings",
    "5": "Segment 5 block CSV settings",
    "6": "Segment 6 run setup settings",
}

PROFILE_GATE_SEGMENTS = ("0", "1", "2", "3", "4")

MISSING_KEYWORDS = (
    "exact",
    "licensed",
    "proprietary",
    "asset",
    "source",
    "soundforge",
    "gain",
    "envelope",
    "calibration",
    "voice-key",
    "response capture",
    "hrtf",
    "apparatus-specific",
    "provenance",
    "source database",
)

STRUCTURAL_KEYWORDS = (
    "scheduler",
    "direction-coupled",
    "tactile-only t0/t6",
    "multi-speaker",
    "seven-speaker",
    "16-speaker",
    "speaker-array",
    "speaker array",
    "amplitude control",
    "amplitude field",
    "switching/timing",
    "speaker switching",
    "body-scaled",
    "coordinate frame",
    "lateralized hand coordinate",
    "trajectory",
    "hemifield",
    "unity",
    "3d tune-in",
)

NON_BLOCKING_CONTEXT_PATTERNS = (
    "clinical group",
    "group/session metadata",
    "prosthesis-worn state",
    "tested limb/body-part assignment",
    "pre/post intervention phase order",
    "tool-use versus pointing-control block factor",
    "body-representation co-task metadata",
    "wheelchair training condition",
    "front/back block factor",
    "front/back block factors",
    "flat versus dynamic condition as block factor",
    "treadmill state",
    "optic flow condition",
    "ordered pre-training/training/post-training phase model",
    "training train structure and timing",
    "other-person/mannequin context",
    "economic-game manipulation",
    "social context",
    "emotional ratings",
    "sound-specific emotional validation",
)

NON_BLOCKING_PROCEDURE_PATTERNS = (
    "randomization",
    "randomisation",
    "random seed",
    "block order",
    "block-order",
    "counterbalanc",
)

CORE_ACCEPTANCE_KEYWORDS = (
    "stimulus",
    "sound",
    "audio",
    "tone",
    "noise",
    "source",
    "asset",
    "trajectory",
    "distance",
    "duration",
    "timing",
    "iti",
    "jitter",
    "soa",
    "baseline",
    "catch",
    "repetition",
    "trial count",
    "tactile",
    "response",
    "calibration",
    "gain",
    "envelope",
    "speaker",
    "hrtf",
    "renderer",
    "trigger",
)


def profile_variant_labels(templates: Iterable[StudyTemplate]) -> dict[str, str]:
    """Return A/B/C labels for multi-variant papers while preserving IDs."""

    groups: dict[str, list[StudyTemplate]] = defaultdict(list)
    for template in templates:
        groups[_paper_group_key(template)].append(template)
    labels: dict[str, str] = {}
    for group in groups.values():
        if len(group) <= 1:
            labels[group[0].template_id] = ""
            continue
        for index, template in enumerate(sorted(group, key=lambda item: item.template_id)):
            labels[template.template_id] = chr(ord("A") + index)
    return labels


def build_profile_parameters_manifest(
    template: StudyTemplate,
    *,
    source_assets: list[dict[str, Any]],
    profile_dir: Path,
    variant_label: str = "",
) -> dict[str, Any]:
    """Create the canonical per-profile parameter/readiness manifest."""

    design = template.design
    field_inventory: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    unsupported: list[dict[str, str]] = []

    def record(
        segment: str,
        parameter: str,
        status: str,
        value: Any = "",
        note: str = "",
    ) -> None:
        field_inventory.append(
            {
                "segment": segment,
                "segment_label": SEGMENT_LABELS.get(str(segment), f"Segment {segment}"),
                "parameter": parameter,
                "status": status,
                "value": value,
                "note": note,
            }
        )
        if status == STATUS_MISSING:
            missing.append({"segment": str(segment), "parameter": parameter, "reason": note or parameter})
        elif status == STATUS_UNSUPPORTED:
            unsupported.append({"segment": str(segment), "parameter": parameter, "reason": note or parameter})

    _record_profile_identity_fields(template, record)
    _record_core_fields(design, source_assets, record)
    _record_gap_fields(template, record)

    validation_warnings = validate_design(design)
    for warning in validation_warnings:
        record("6", "current_design_validation", STATUS_MISSING, "", warning)

    partial_without_gaps = (
        template.verification_status == "partial"
        and not _implementation_gaps(template)
        and not bool(template.reference_parameters.get("profile_check_complete", False))
        and not missing
        and not unsupported
    )
    if partial_without_gaps:
        record(
            "0",
            "partial_profile_gap_notes",
            STATUS_MISSING,
            "",
            "Profile is marked partial but does not yet enumerate paper-level missing parameters.",
        )

    segment_gate = _segment_profile_checks(field_inventory)
    blocking_missing = _gate_items(missing)
    blocking_unsupported = _gate_items(unsupported)
    gui_materializable = _gui_materializable(design, source_assets, blocking_missing, blocking_unsupported)
    if blocking_unsupported:
        primary_category = CATEGORY_TOOLKIT_STRUCTURAL_GAP
        runner_readiness = BLOCKED_UNSUPPORTED
    elif blocking_missing:
        primary_category = CATEGORY_MISSING_PUBLICATION_PARAMETERS
        runner_readiness = BLOCKED_MISSING
    else:
        primary_category = CATEGORY_GUI_RECREATABLE
        runner_readiness = READY_RUNNER

    profile_checks_passed = primary_category == CATEGORY_GUI_RECREATABLE and gui_materializable and segment_gate["passed"]
    finished_profile = runner_readiness == READY_RUNNER and profile_checks_passed and segment_gate["passed"]
    segment_artifacts = _segment_artifact_summary(profile_dir, source_assets, design)
    return {
        "schema": PROFILE_PARAMETERS_SCHEMA,
        "template_id": template.template_id,
        "title": template.title,
        "citation": template.citation,
        "doi": template.doi,
        "source_url": template.source_url,
        "verification_status": template.verification_status,
        "paper_group_key": _paper_group_key(template),
        "visible_variant_label": variant_label,
        "variant_display": _variant_display(template.title, variant_label),
        "recreation_status": {
            "primary_category": primary_category,
            "category_label": CATEGORY_LABELS[primary_category],
            "runner_readiness": runner_readiness,
            "profile_checks_passed": profile_checks_passed,
            "gui_recreatable": primary_category == CATEGORY_GUI_RECREATABLE,
            "segment_0_to_4_profile_checks_passed": segment_gate["passed"],
            "segment_1_to_6_materializable": gui_materializable,
            "finished_profile": finished_profile,
            "segment_6_launchable": finished_profile,
            "profile_completion_status": "finished_segment_6_launchable" if finished_profile else "unfinished_preload",
            "missing_parameter_count": len(blocking_missing),
            "unsupported_structure_count": len(blocking_unsupported),
        },
        "segment_0_to_4_profile_checks": segment_gate,
        "field_inventory": field_inventory,
        "missing_publication_parameters": missing,
        "unsupported_toolkit_structures": unsupported,
        "generated_segment_artifacts": segment_artifacts,
        "provenance": template.provenance,
        "notes": (
            "This manifest audits recreation inside the PPS Toolkit GUI. It distinguishes toolkit-generated "
            "recreations of reported parameters from the original authors' exact stimulus set."
        ),
    }


def profile_summary_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    status = dict(manifest.get("recreation_status") or {})
    missing = list(manifest.get("missing_publication_parameters") or [])
    unsupported = list(manifest.get("unsupported_toolkit_structures") or [])
    return {
        "template_id": manifest.get("template_id", ""),
        "title": manifest.get("title", ""),
        "citation": manifest.get("citation", ""),
        "doi": manifest.get("doi", ""),
        "verification_status": manifest.get("verification_status", ""),
        "visible_variant_label": manifest.get("visible_variant_label", ""),
        "variant_display": manifest.get("variant_display", manifest.get("title", "")),
        "primary_category": status.get("primary_category", CATEGORY_MISSING_PUBLICATION_PARAMETERS),
        "category_label": status.get("category_label", CATEGORY_LABELS[CATEGORY_MISSING_PUBLICATION_PARAMETERS]),
        "runner_readiness": status.get("runner_readiness", BLOCKED_MISSING),
        "profile_checks_passed": bool(status.get("profile_checks_passed", False)),
        "gui_recreatable": bool(status.get("gui_recreatable", False)),
        "segment_0_to_4_profile_checks_passed": bool(status.get("segment_0_to_4_profile_checks_passed", False)),
        "segment_1_to_6_materializable": bool(status.get("segment_1_to_6_materializable", False)),
        "finished_profile": bool(status.get("finished_profile", False)),
        "segment_6_launchable": bool(status.get("segment_6_launchable", False)),
        "profile_completion_status": status.get("profile_completion_status", "unfinished_preload"),
        "missing_parameter_count": int(status.get("missing_parameter_count") or len(missing)),
        "unsupported_structure_count": int(status.get("unsupported_structure_count") or len(unsupported)),
        "segment_0_to_4_profile_checks": manifest.get("segment_0_to_4_profile_checks", {}),
        "missing_publication_parameters": missing,
        "unsupported_toolkit_structures": unsupported,
        "profile_parameters_manifest": f"assets/preloads/{manifest.get('template_id', '')}/01_profile/profile_parameters_manifest.json",
    }


def build_profile_recreation_status(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = [profile_summary_from_manifest(manifest) for manifest in manifests]
    categories = {
        CATEGORY_GUI_RECREATABLE: [
            profile["template_id"]
            for profile in profiles
            if profile.get("primary_category") == CATEGORY_GUI_RECREATABLE
        ],
        CATEGORY_MISSING_PUBLICATION_PARAMETERS: [
            profile["template_id"]
            for profile in profiles
            if int(profile.get("missing_parameter_count") or 0) > 0
        ],
        CATEGORY_TOOLKIT_STRUCTURAL_GAP: [
            profile["template_id"]
            for profile in profiles
            if int(profile.get("unsupported_structure_count") or 0) > 0
        ],
    }
    return {
        "schema": PROFILE_RECREATION_STATUS_SCHEMA,
        "profile_count": len(profiles),
        "categories": categories,
        "category_labels": CATEGORY_LABELS,
        "profiles": profiles,
    }


def render_profile_recreation_status_markdown(status: dict[str, Any]) -> str:
    profiles = list(status.get("profiles") or [])
    lines = [
        "# Published Study Recreation Status",
        "",
        "This report separates three outcomes for catalogued audio-tactile PPS profiles:",
        "",
        "- `GUI-recreatable`: Segment 0-4 profile parameters are complete and the toolkit can natively materialize later run artifacts.",
        "- `Missing publication parameters`: required details or original assets are not reported or not encoded with enough specificity.",
        "- `Toolkit structural gap`: the study uses an audiotactile task-execution structure, audio rendering mode, tactile/response option, or apparatus geometry that the current dashboard/backend does not yet model.",
        "",
        "Only profiles in `GUI-recreatable` pass the Segment 0-4 profile checks for runnable toolkit inclusion. Segments after 4 are native app materialization and runner handoff, so they do not reject a paper profile unless an earlier profile segment is incomplete.",
        "",
        "Structural gaps are limited to standardization constraints in the PPS task itself: trial-family and baseline logic, auditory stimulus type/provenance/rendering/gain law, spatial trajectory and apparatus geometry, tactile site/channel/calibration, response capture, and core timing/repetition parameters.",
        "",
        "For integration decisions, the relevant question is whether the toolkit has a profile input/schema slot for the audiotactile task mechanic. The required published parameters must be complete through Segment 4: profile metadata/provenance, stimulus type/assets/trajectory, trial sequence including ITI or jitter boxes when task-relevant, SOAs and baseline/tactile strategy, and trial repetition count.",
        "",
        "Two-speaker analog looming/receding apparatus is treated as source-apparatus provenance, not as a separate audio-source type. When the paper reports enough trajectory/timing/source parameters, the profile recreates that task as a binaural spatialized trajectory; exact original gain/envelope files are tracked as missing provenance only when exact author-stimulus equivalence is required.",
        "",
        "Ordinary trial randomization and block order are treated as reproducible runner defaults, not publication-acceptance blockers, unless the paper's PPS task depends on a specific ITI/jitter, hazard, baseline, or repetition schedule.",
        "",
        "A recreated profile is a toolkit recreation of reported parameters, not a claim to reproduce the authors' exact original stimulus set.",
        "Clinical populations, interventions, and non-audiotactile experimental context are retained as notes but do not block profile inclusion unless they alter the audiotactile PPS task execution itself.",
        "",
    ]
    for category, label in CATEGORY_LABELS.items():
        selected_ids = set((status.get("categories") or {}).get(category, []))
        selected = [profile for profile in profiles if profile.get("template_id") in selected_ids]
        lines.extend([f"## {label}", ""])
        if not selected:
            lines.extend(["No profiles currently fall in this category.", ""])
            continue
        lines.extend(["| Profile | Variant | Status | Main reasons |", "|---|---|---|---|"])
        for profile in selected:
            variant = profile.get("visible_variant_label") or "-"
            reasons = _summary_reasons(profile, category)
            lines.append(
                "| {profile} | {variant} | {readiness} | {reasons} |".format(
                    profile=_markdown_escape(str(profile.get("template_id") or "")),
                    variant=_markdown_escape(str(variant)),
                    readiness=_markdown_escape(str(profile.get("runner_readiness") or "")),
                    reasons=_markdown_escape(reasons),
                )
            )
        lines.append("")
    lines.extend(["## Machine-Readable Source", "", "- `assets/preloads/profile_recreation_status.json`"])
    return "\n".join(lines).rstrip() + "\n"


def load_profile_recreation_status(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root) / "assets" / "preloads" / "profile_recreation_status.json"
    if not path.exists():
        return {"schema": PROFILE_RECREATION_STATUS_SCHEMA, "profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def profile_recreation_entry(template_id: str, repo_root: Path) -> dict[str, Any]:
    for profile in load_profile_recreation_status(repo_root).get("profiles", []):
        if profile.get("template_id") == template_id:
            return dict(profile)
    return {}


def _record_profile_identity_fields(template: StudyTemplate, record: Any) -> None:
    record(
        "0",
        "profile_identity",
        STATUS_REPORTED if template.template_id and template.title else STATUS_MISSING,
        {"template_id": template.template_id, "title": template.title},
        "Profile ID and title are encoded." if template.template_id and template.title else "Profile ID/title is incomplete.",
    )
    record(
        "0",
        "publication_reference",
        STATUS_REPORTED if template.citation or template.doi or template.source_url else STATUS_DEFAULTED,
        {"citation": template.citation, "doi": template.doi, "source_url": template.source_url},
        "Publication reference metadata is encoded."
        if template.citation or template.doi or template.source_url
        else "No publication reference is required for this non-published local profile.",
    )
    record(
        "0",
        "profile_parameter_provenance",
        STATUS_REPORTED if template.provenance or template.reference_parameters else STATUS_DEFAULTED,
        len(template.provenance) + len(template.reference_parameters),
        "Profile provenance/reference parameters are encoded."
        if template.provenance or template.reference_parameters
        else "No extra provenance fields are declared for this profile.",
    )


def _record_core_fields(
    design: StimulusDesign,
    source_assets: list[dict[str, Any]],
    record: Any,
) -> None:
    protocol = design.protocol
    record(
        "1",
        "source_stimulus_inventory",
        STATUS_REPORTED if source_assets else STATUS_MISSING,
        len(source_assets),
        "Prebaked/profile source assets available." if source_assets else "No source assets are available for Segment 1.",
    )
    snapshots = [asset.get("trajectory_snapshot") for asset in source_assets if asset.get("trajectory_snapshot")]
    record(
        "1",
        "trajectory_snapshots",
        STATUS_REPORTED if snapshots else STATUS_MISSING,
        len(snapshots),
        "Source-level trajectory snapshots are available." if snapshots else "No source-level trajectory snapshots are available.",
    )
    durations = [asset.get("duration_s") for asset in source_assets if float(asset.get("duration_s") or 0.0) > 0.0]
    record(
        "1",
        "stimulus_duration",
        STATUS_REPORTED if durations else STATUS_INFERRED,
        sorted({round(float(value), 6) for value in durations}) or round(design.trajectory.total_duration_s, 6),
        "Duration comes from generated WAV metadata." if durations else "Duration inferred from trajectory defaults.",
    )

    row_count = sum(1 for strip in protocol.trial_strips if strip.elements)
    record(
        "2",
        "trial_sequence_rows",
        STATUS_REPORTED if row_count else STATUS_UNSUPPORTED,
        row_count,
        "Current Segment 2 row/box representation is encoded."
        if row_count
        else "Profile has not been encoded as current Segment 2 row/box trial-sequence design.",
    )
    jitter_values = [
        value
        for strip in protocol.trial_strips
        for element in strip.elements
        for value in element.jitter_values_ms
    ]
    record(
        "2",
        "jitter_values_ms",
        STATUS_REPORTED if jitter_values else STATUS_DEFAULTED,
        jitter_values,
        "Explicit jitter values encoded." if jitter_values else "No explicit jitter box is encoded.",
    )
    record(
        "2",
        "iti_jitter_policy",
        STATUS_REPORTED if jitter_values else STATUS_DEFAULTED,
        "jitter/iti box" if jitter_values else "no explicit Segment 2 ITI/jitter box",
        "Segment 2 encodes explicit ITI/jitter timing values."
        if jitter_values
        else "No explicit ITI/jitter box is encoded; missing ITI/jitter is only a blocker when listed as a publication gap.",
    )
    record(
        "3",
        "soa_values_ms",
        STATUS_REPORTED if protocol.soa_values_ms else STATUS_MISSING,
        list(protocol.soa_values_ms),
        "SOA values are encoded." if protocol.soa_values_ms else "No SOA values are encoded.",
    )
    record(
        "3",
        "tactile_sites",
        STATUS_REPORTED if protocol.tactile_sites else STATUS_DEFAULTED,
        list(protocol.tactile_sites),
        "Tactile site labels are encoded." if protocol.tactile_sites else "Toolkit default tactile site will be used.",
    )
    record(
        "3",
        "baseline_mode",
        STATUS_REPORTED if protocol.baseline_strategy else STATUS_DEFAULTED,
        protocol.baseline_strategy or "none/default",
        "Baseline strategy is encoded." if protocol.baseline_strategy else "No paper-specific baseline strategy is encoded.",
    )
    catch_value: Any = protocol.catch_trials_exact if protocol.catch_trials_exact is not None else protocol.catch_trial_percentage
    record(
        "3",
        "catch_mode",
        STATUS_REPORTED if protocol.include_catch_trials or catch_value else STATUS_DEFAULTED,
        catch_value,
        "Catch settings are encoded." if protocol.include_catch_trials or catch_value else "No catch trials are configured.",
    )
    repetition_defaults = dict(getattr(protocol, "trial_pool_repetition_defaults", {}) or {})
    record(
        "4",
        "trial_pool_repetitions",
        STATUS_REPORTED if repetition_defaults else STATUS_INFERRED,
        repetition_defaults or protocol.repetitions_per_condition,
        "Segment 4 repetition defaults are encoded."
        if repetition_defaults
        else "Segment 4 can infer repetitions from repetitions_per_condition.",
    )
    record(
        "5",
        "block_count",
        STATUS_REPORTED if protocol.blocks else STATUS_DEFAULTED,
        protocol.blocks,
        "Block count is encoded." if protocol.blocks else "Block count is a runner default and is not part of the publication acceptance gate.",
    )
    record(
        "5",
        "row_order_constraints",
        STATUS_REPORTED if has_trial_strips(protocol) else STATUS_UNSUPPORTED,
        row_count,
        "Row order can be preserved through Segment 5."
        if has_trial_strips(protocol)
        else "Segment 5 row-order preservation requires Segment 2 row folders.",
    )
    record(
        "6",
        "participants",
        STATUS_REPORTED if protocol.participants else STATUS_DEFAULTED,
        protocol.participants,
        "Participant count default is encoded." if protocol.participants else "Participant count will use dashboard default.",
    )
    record(
        "6",
        "experiment_parts",
        STATUS_DEFAULTED,
        "1 part",
        "Current dashboard default; phase/intervention context is non-blocking unless it changes the audiotactile PPS task execution.",
    )


def _record_gap_fields(template: StudyTemplate, record: Any) -> None:
    for gap in _implementation_gaps(template):
        gap_statuses = _classify_gap(gap)
        if not gap_statuses:
            gap_statuses = [STATUS_MISSING]
        for status in gap_statuses:
            segment = _gap_segment(gap)
            parameter = "profile_gap"
            record(segment, parameter, status, gap, gap)


def _segment_profile_checks(field_inventory: list[dict[str, Any]]) -> dict[str, Any]:
    checks = []
    for segment in PROFILE_GATE_SEGMENTS:
        fields = [item for item in field_inventory if str(item.get("segment")) == segment]
        blockers = [
            {
                "parameter": str(item.get("parameter") or ""),
                "status": str(item.get("status") or ""),
                "reason": str(item.get("note") or item.get("parameter") or ""),
            }
            for item in fields
            if item.get("status") in {STATUS_MISSING, STATUS_UNSUPPORTED}
        ]
        checks.append(
            {
                "segment": segment,
                "segment_label": SEGMENT_LABELS[segment],
                "passed": bool(fields) and not blockers,
                "field_count": len(fields),
                "blocking_reasons": blockers,
            }
        )
    return {
        "gate": "segments_0_to_4",
        "passed": all(check["passed"] for check in checks),
        "segments": checks,
    }


def _gate_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    gate = set(PROFILE_GATE_SEGMENTS)
    return [item for item in items if str(item.get("segment") or "") in gate]


def _implementation_gaps(template: StudyTemplate) -> list[str]:
    gaps = template.reference_parameters.get("implementation_gaps", [])
    if isinstance(gaps, str):
        return [gaps]
    if isinstance(gaps, list):
        return [str(item) for item in gaps if str(item).strip()]
    return []


def _classify_gap(gap: str) -> list[str]:
    text = gap.lower()
    if _non_blocking_context_gap(text):
        return [STATUS_DEFAULTED]
    if _non_blocking_procedure_gap(text):
        return [STATUS_DEFAULTED]
    statuses: list[str] = []
    if any(keyword in text for keyword in STRUCTURAL_KEYWORDS):
        statuses.append(STATUS_UNSUPPORTED)
    if any(keyword in text for keyword in MISSING_KEYWORDS):
        statuses.append(STATUS_MISSING)
    return statuses


def _non_blocking_context_gap(text: str) -> bool:
    return any(pattern in text for pattern in NON_BLOCKING_CONTEXT_PATTERNS)


def _non_blocking_procedure_gap(text: str) -> bool:
    has_procedure_gap = any(pattern in text for pattern in NON_BLOCKING_PROCEDURE_PATTERNS)
    has_core_parameter = any(keyword in text for keyword in CORE_ACCEPTANCE_KEYWORDS)
    return has_procedure_gap and not has_core_parameter


def _gap_segment(gap: str) -> str:
    text = gap.lower()
    if any(keyword in text for keyword in ("source", "asset", "sound", "speaker", "hrtf", "envelope", "gain")):
        return "1"
    if any(keyword in text for keyword in ("scheduler", "row", "trial", "jitter", "iti")):
        return "2"
    if any(keyword in text for keyword in ("tactile", "baseline", "catch", "calibration", "response")):
        return "3"
    if any(keyword in text for keyword in ("block", "direction", "break")):
        return "5"
    if any(keyword in text for keyword in ("phase", "training", "intervention", "session", "group", "prosthesis")):
        return "6"
    return "0"


def _gui_materializable(
    design: StimulusDesign,
    source_assets: list[dict[str, Any]],
    missing: list[dict[str, str]],
    unsupported: list[dict[str, str]],
) -> bool:
    return bool(
        source_assets
        and has_trial_strips(design.protocol)
        and design.protocol.soa_values_ms
        and not missing
        and not unsupported
    )


def _segment_artifact_summary(profile_dir: Path, source_assets: list[dict[str, Any]], design: StimulusDesign) -> dict[str, Any]:
    return {
        "01_profile": {
            "profile_metadata": _rel_if_possible(profile_dir / "01_profile" / "profile_metadata.json"),
            "profile_parameters_manifest": _rel_if_possible(profile_dir / "01_profile" / "profile_parameters_manifest.json"),
        },
        "02_looming_stimuli": {
            "stimulus_sources": _rel_if_possible(profile_dir / "02_looming_stimuli" / "stimulus_sources.json"),
            "trajectory_inventory": _rel_if_possible(profile_dir / "02_looming_stimuli" / "trajectory_inventory.json"),
            "asset_count": len(source_assets),
        },
        "03_baseline_strategy": {
            "baseline_strategy": _rel_if_possible(profile_dir / "03_baseline_strategy" / "baseline_strategy.json"),
        },
        "04_trial_designer": {
            "trial_design": _rel_if_possible(profile_dir / "04_trial_designer" / "trial_design.json"),
            "trial_row_count": sum(1 for strip in design.protocol.trial_strips if strip.elements),
        },
        "05_run_setup": {
            "run_defaults": _rel_if_possible(profile_dir / "05_run_setup" / "run_defaults.json"),
            "block_count": design.protocol.blocks,
            "participant_count": design.protocol.participants,
        },
        "local_segment_0_to_4_profile_gate": {
            "mode": "publication_parameter_check",
            "scope": "Segments 0-4 must have no missing or unsupported profile parameters before native app materialization.",
        },
        "local_segment_1_to_6_materialization": {
            "mode": "local_companion_batch",
            "tool": "tools/materialize_profile_segments.py",
            "tracked_in_git": False,
        },
    }


def _rel_if_possible(path: Path) -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        return str(Path(path).resolve().relative_to(root).as_posix())
    except ValueError:
        return str(path)


def _paper_group_key(template: StudyTemplate) -> str:
    if template.doi:
        return f"doi:{template.doi.lower().strip()}"
    text = re.sub(r"\s+", " ", template.citation.lower()).strip()
    return f"citation:{text}" if text else f"template:{template.template_id}"


def _variant_display(title: str, variant_label: str) -> str:
    return f"{title} - Variant {variant_label}" if variant_label else title


def _summary_reasons(profile: dict[str, Any], category: str) -> str:
    reasons: list[str] = []
    keys = {
        CATEGORY_MISSING_PUBLICATION_PARAMETERS: ("missing_publication_parameters",),
        CATEGORY_TOOLKIT_STRUCTURAL_GAP: ("unsupported_toolkit_structures",),
    }.get(category, ("unsupported_toolkit_structures", "missing_publication_parameters"))
    for key in keys:
        for item in profile.get(key, [])[:3]:
            reason = str(item.get("reason") or item.get("parameter") or "").strip()
            if reason:
                reasons.append(reason)
    if not reasons:
        return "All required current-GUI fields are present and materializable."
    suffix = "" if len(reasons) <= 3 else f"; +{len(reasons) - 3} more"
    return "; ".join(reasons[:3]) + suffix


def _markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
