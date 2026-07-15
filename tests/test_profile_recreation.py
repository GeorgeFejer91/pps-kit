from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from peripersonal_space_toolkit.profile_recreation import (
    PROFILE_PARAMETERS_SCHEMA,
    PROFILE_RECREATION_STATUS_SCHEMA,
    STATUS_DEFAULTED,
    STATUS_INFERRED,
    STATUS_MISSING,
    STATUS_REPORTED,
    STATUS_UNSUPPORTED,
    _classify_gap,
)
from peripersonal_space_toolkit.templates import DEFAULT_STUDY_TEMPLATE_ID, load_templates


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_SCRIPT_DIR = ROOT / "validation_protocols" / "scripts"
STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID = "study5_dynaspace_lateral_45_pps"


def _load_validation_script(name: str):
    path = VALIDATION_SCRIPT_DIR / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_profile_recreation_manifests_cover_all_current_templates():
    root = ROOT
    templates = load_templates(root / "study_templates")
    template_ids = {template.template_id for template in templates}
    status = json.loads((root / "assets" / "preloads" / "profile_recreation_status.json").read_text(encoding="utf-8"))

    assert len(templates) == 24
    assert status["schema"] == PROFILE_RECREATION_STATUS_SCHEMA
    assert status["profile_count"] == len(templates)
    assert {profile["template_id"] for profile in status["profiles"]} == template_ids

    categorized = set().union(*(set(values) for values in status["categories"].values()))
    assert categorized == template_ids
    assert status["categories"]["gui_recreatable"]
    assert status["categories"]["missing_publication_parameters"]
    assert len(status["categories"]["missing_publication_parameters"]) == 8
    assert len(status["categories"]["toolkit_structural_gap"]) == 0

    allowed_statuses = {
        STATUS_REPORTED,
        STATUS_INFERRED,
        STATUS_DEFAULTED,
        STATUS_MISSING,
        STATUS_UNSUPPORTED,
    }
    for template_id in template_ids:
        manifest_path = root / "assets" / "preloads" / template_id / "01_profile" / "profile_parameters_manifest.json"
        assert manifest_path.exists(), template_id
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema"] == PROFILE_PARAMETERS_SCHEMA
        assert manifest["template_id"] == template_id
        gate = manifest["segment_0_to_4_profile_checks"]
        assert gate["gate"] == "segments_0_to_4"
        assert {item["segment"] for item in gate["segments"]} == {"0", "1", "2", "3", "4"}
        assert {item["status"] for item in manifest["field_inventory"]} <= allowed_statuses
        assert not any(
            item["status"] == STATUS_UNSUPPORTED
            and (
                "current Segment 2 row/box" in item.get("note", "")
                or "row-order preservation" in item.get("note", "")
            )
            for item in manifest["field_inventory"]
        )
        blocking_reasons = {
            item.get("reason", "")
            for key in ("missing_publication_parameters", "unsupported_toolkit_structures")
            for item in manifest.get(key, [])
        }
        assert "clinical group/session metadata" not in blocking_reasons
        assert "prosthesis-worn state" not in blocking_reasons
        assert "pre/post intervention phase order" not in blocking_reasons
        assert "wheelchair training condition" not in blocking_reasons
        assert "treadmill state" not in blocking_reasons
        assert "optic flow condition" not in blocking_reasons
        assert "emotional ratings" not in blocking_reasons
        assert "sound-specific emotional validation" not in blocking_reasons
        assert _classify_gap("exact randomization sequence") == [STATUS_DEFAULTED]
        assert _classify_gap("counterbalanced block order from random seed") == [STATUS_DEFAULTED]
        assert STATUS_MISSING in _classify_gap("exact trial count and ITI table")


def test_profile_recreation_status_distinguishes_ready_missing_and_structural_profiles():
    root = ROOT
    status = json.loads((root / "assets" / "preloads" / "profile_recreation_status.json").read_text(encoding="utf-8"))
    profiles = {profile["template_id"]: profile for profile in status["profiles"]}

    study5 = profiles[DEFAULT_STUDY_TEMPLATE_ID]
    assert study5["primary_category"] == "gui_recreatable"
    assert study5["publication_status"] == "unpublished_lab_profile"
    assert study5["runner_readiness"] == "ready"
    assert study5["profile_checks_passed"] is True
    assert study5["segment_0_to_4_profile_checks_passed"] is True
    assert study5["missing_parameter_count"] == 0
    assert study5["unsupported_structure_count"] == 0
    assert len(status["categories"]["gui_recreatable"]) == 16

    study5_lateral = profiles[STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID]
    assert study5_lateral["primary_category"] == "gui_recreatable"
    assert study5_lateral["publication_status"] == "unpublished_lab_profile"
    assert study5_lateral["runner_readiness"] == "ready"
    assert study5_lateral["profile_checks_passed"] is True
    assert study5_lateral["segment_0_to_4_profile_checks_passed"] is True
    assert study5_lateral["missing_parameter_count"] == 0
    assert study5_lateral["unsupported_structure_count"] == 0

    pfeiffer = profiles["pfeiffer_2018_lateral_perihead_left_to_right"]
    assert pfeiffer["primary_category"] == "gui_recreatable"
    assert pfeiffer["runner_readiness"] == "ready"
    assert pfeiffer["profile_checks_passed"] is True
    assert pfeiffer["segment_0_to_4_profile_checks_passed"] is True

    serino_trunk = profiles["serino_2015_peri_trunk_exp1"]
    assert serino_trunk["primary_category"] == "gui_recreatable"
    assert serino_trunk["profile_checks_passed"] is True
    assert serino_trunk["segment_0_to_4_profile_checks_passed"] is True

    dynaspace = profiles["roussel_2025_dynaspace_mobile_pps"]
    assert dynaspace["primary_category"] == "gui_recreatable"
    assert dynaspace["publication_status"] == "published"
    assert dynaspace["runner_readiness"] == "ready"
    assert dynaspace["profile_checks_passed"] is True
    assert dynaspace["segment_0_to_4_profile_checks_passed"] is True
    assert dynaspace["missing_parameter_count"] == 0
    assert dynaspace["unsupported_structure_count"] == 0

    canzoneri = profiles["canzoneri_2012_dynamic_sounds"]
    assert canzoneri["primary_category"] == "gui_recreatable"
    assert canzoneri["runner_readiness"] == "ready"
    assert canzoneri["profile_checks_passed"] is True
    assert canzoneri["segment_0_to_4_profile_checks_passed"] is True
    assert canzoneri["missing_parameter_count"] == 0
    assert canzoneri["unsupported_structure_count"] == 0

    tonelli = profiles["tonelli_2019_echolocation"]
    assert tonelli["primary_category"] == "gui_recreatable"
    assert tonelli["runner_readiness"] == "ready"
    assert tonelli["profile_checks_passed"] is True
    assert tonelli["segment_0_to_4_profile_checks_passed"] is True
    assert tonelli["missing_parameter_count"] == 0
    assert tonelli["unsupported_structure_count"] == 0

    serino_front_back = profiles["serino_2015_front_back_trunk_exp2"]
    assert serino_front_back["primary_category"] == "gui_recreatable"
    assert serino_front_back["runner_readiness"] == "ready"
    assert serino_front_back["profile_checks_passed"] is True
    assert serino_front_back["segment_0_to_4_profile_checks_passed"] is True
    assert serino_front_back["missing_parameter_count"] == 0
    assert serino_front_back["unsupported_structure_count"] == 0

    galli = profiles["galli_2015_wheelchair_full_body"]
    assert galli["primary_category"] == "gui_recreatable"
    assert galli["runner_readiness"] == "ready"
    assert galli["profile_checks_passed"] is True
    assert galli["segment_0_to_4_profile_checks_passed"] is True
    assert galli["missing_parameter_count"] == 0
    assert galli["unsupported_structure_count"] == 0

    serino_hand = profiles["serino_2015_peri_hand_exp3"]
    assert serino_hand["primary_category"] == "gui_recreatable"
    assert serino_hand["runner_readiness"] == "ready"
    assert serino_hand["profile_checks_passed"] is True
    assert serino_hand["segment_0_to_4_profile_checks_passed"] is True
    assert serino_hand["missing_parameter_count"] == 0
    assert serino_hand["unsupported_structure_count"] == 0

    report = (root / "docs" / "PUBLISHED_STUDY_RECREATION_STATUS.md").read_text(encoding="utf-8")
    assert "## GUI-recreatable" in report
    assert "## Missing publication parameters" in report
    assert "## Toolkit structural gap" in report
    assert "Clinical populations, interventions, and non-audiotactile experimental context" in report
    assert "Ordinary trial randomization and block order" in report

    tex_report = (root / "docs" / "audit_report.tex").read_text(encoding="utf-8")
    assert "Published-paper profiles passing checks & 14" in tex_report
    assert "study5" in tex_report and "box" in tex_report and "breathing" in tex_report
    assert "No visible GUI progress indicator" in tex_report
    assert "Clinical populations, interventions, non-audiotactile stimuli" in tex_report


def test_preload_segment2_trial_designs_are_never_empty():
    root = ROOT
    templates = load_templates(root / "study_templates")

    for template in templates:
        trial_design_path = (
            root
            / "assets"
            / "preloads"
            / template.template_id
            / "04_trial_designer"
            / "trial_design.json"
        )
        trial_design = json.loads(trial_design_path.read_text(encoding="utf-8"))
        strips = trial_design.get("trial_strips") or []
        assert strips, template.template_id
        for strip in strips:
            assert strip.get("elements"), (template.template_id, strip.get("label"))
            for element in strip["elements"]:
                if element.get("kind") in {"fixed_audio", "looming_stimulus"}:
                    assert element.get("source_labels"), (
                        template.template_id,
                        strip.get("label"),
                        element.get("label"),
                    )


def test_barumerli_segment2_expands_analog_motion_to_binaural_source_variants():
    root = ROOT
    trial_design = json.loads(
        (
            root
            / "assets"
            / "preloads"
            / "barumerli_2026_arm_movement_exp1"
            / "04_trial_designer"
            / "trial_design.json"
        ).read_text(encoding="utf-8")
    )
    labels = trial_design["trial_strips"][0]["elements"][0]["source_labels"]

    assert labels == ["Pink moving sound", "Pink moving sound - receding"]


def test_protocol12_matrix_targets_ready_published_profiles_and_blocked_samples():
    matrix = _load_validation_script("run_profile_recreation_interface_matrix.py")
    status = json.loads((ROOT / "assets" / "preloads" / "profile_recreation_status.json").read_text(encoding="utf-8"))

    ready_published = matrix._target_template_ids(status, profile_set="ready-published")
    ready_all = matrix._target_template_ids(status, profile_set="ready-all")
    blocked_samples = matrix._default_blocked_samples(status, exclude=set(ready_published))

    assert DEFAULT_STUDY_TEMPLATE_ID not in ready_published
    assert STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID not in ready_published
    assert DEFAULT_STUDY_TEMPLATE_ID in ready_all
    assert STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID in ready_all
    assert len(ready_published) == 14
    assert set(ready_published) < set(ready_all)
    assert len(blocked_samples) == 1

    profiles = {profile["template_id"]: profile for profile in status["profiles"]}
    assert any(profiles[item]["missing_parameter_count"] > 0 for item in blocked_samples)
    assert all(profiles[item]["unsupported_structure_count"] == 0 for item in blocked_samples)


def test_protocol12_matrix_metadata_only_report_accepts_ready_and_blocked(tmp_path: Path):
    matrix = _load_validation_script("run_profile_recreation_interface_matrix.py")

    report = matrix.run_matrix(
        output_dir=tmp_path,
        templates=["pfeiffer_2018_lateral_perihead_left_to_right"],
        blocked_templates=["taffou_2014_cynophobic_rear_looming"],
        metadata_only=True,
    )

    assert report["schema"] == matrix.SCHEMA
    assert report["passed"]
    assert report["ready_profile_count"] == 1
    assert report["blocked_profile_sample_count"] == 1
    assert report["profile_results"][0]["gate_passed"]
    assert report["profile_results"][0]["materialization"]["status"] == "skipped"
    assert report["blocked_results"][0]["blocked"]
    assert (tmp_path / "profile_recreation_interface_matrix_report.json").exists()
    assert (tmp_path / "profile_recreation_interface_matrix_report.md").exists()


def test_protocol12_matrix_materializes_session_packages_under_each_profile_root(tmp_path: Path):
    matrix = _load_validation_script("run_profile_recreation_interface_matrix.py")

    report = matrix.run_matrix(
        output_dir=tmp_path,
        templates=["roussel_2025_dynaspace_mobile_pps", "matsuda_2021_four_directions"],
        skip_blocked_samples=True,
    )

    assert report["schema"] == matrix.SCHEMA
    assert report["passed"]
    local_criteria = [
        criterion
        for criterion in report["criteria"]
        if criterion["name"].endswith(":participant_package_profile_local")
    ]
    assert len(local_criteria) == 2
    assert all(criterion["passed"] for criterion in local_criteria)

    for result in report["profile_results"]:
        materialization = result["materialization"]
        expected_root = Path(materialization["expected_session_root"]).resolve()
        session_dir = Path(materialization["session_dir"]).resolve()
        session_manifest = Path(materialization["session_manifest_path"]).resolve()

        assert result["template_id"] in str(expected_root)
        assert session_dir == expected_root or expected_root in session_dir.parents
        assert session_manifest == expected_root or expected_root in session_manifest.parents
        assert session_manifest.exists()
