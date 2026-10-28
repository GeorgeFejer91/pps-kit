"""The all-preset audit must not accept a shortened or same-count wrong plan."""
import importlib.util
import copy
import csv
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "validation/scripts/audit_preset_population.py"
spec = importlib.util.spec_from_file_location("preset_population_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def capture():
    rows = [{"trial_pool_index": n, "family": "audio_tactile", "soa_ms": 300,
             "duration_ms": 5000, "tactile_onset_s": 1.3} for n in [1, 2]]
    return {"design": {"study_profile_id": "fixture", "protocol": {"participants": 10}},
            "trial_pool_bake": {"total_count": 2, "preview_rows": rows},
            "block_csv_preview": {"blocks": [{"block_index": 1, "block_label": "Block 1", "trial_count": 2,
                "preview_rows": [{**row, "block_index": 1, "block_trial_index": n} for n, row in enumerate(rows, 1)]}]},
            "custom_workflow": {"ready_to_prepare": True}, "run_sequence_setup": {"experiment_structure": "single"}}


def test_full_plan_preserves_pool_identities_and_timing():
    fixture = capture()
    result = audit.checked_plan("fixture", True, fixture)
    assert result["source_trial_count"] == 2
    assert result["usable_runner_file_verified"] is False
    fixture["block_csv_preview"]["blocks"][0]["preview_rows"][1]["trial_pool_index"] = 1
    with pytest.raises(ValueError, match="preserve every pool row"):
        audit.checked_plan("fixture", True, fixture)


@pytest.mark.parametrize("change", ["truncated", "wrong_timing", "wrong_order"])
def test_rejects_cutdown_or_changed_plan(change):
    fixture = capture()
    block = fixture["block_csv_preview"]["blocks"][0]
    if change == "truncated":
        block["preview_rows"].pop()
    elif change == "wrong_timing":
        block["preview_rows"][0]["tactile_onset_s"] = 0.3
    else:
        block["preview_rows"][0]["block_trial_index"] = 2
    with pytest.raises(ValueError):
        audit.checked_plan("fixture", True, fixture)


def test_gate_success_is_not_a_usable_file_and_identity_mismatch_fails():
    fixture = capture()
    fixture["block_csv_preview"] = {}
    fixture["custom_workflow"]["ready_to_prepare"] = False
    assert audit.checked_plan("fixture", False, fixture)["status"] == "blocked_as_shipped"
    with pytest.raises(ValueError, match="Wrong captured template"):
        audit.checked_plan("different", False, fixture)
    with pytest.raises(ValueError, match="Duplicate"):
        audit.unique_by([{"id": "same"}, {"id": "same"}], "id")


def test_declared_choice_contract_must_survive_even_when_counts_match():
    fixture = capture()
    fixture["design"]["protocol"]["trial_strips"] = [{"label": "Left", "metadata": {
        "correct_response": "left", "response_choice_set": "left,right", "expected_response": "respond"}}]
    for row in fixture["block_csv_preview"]["blocks"][0]["preview_rows"]:
        row.update(row_label="Left", correct_response="left", response_choice_set="left,right", expected_response="respond")
    allowed = {"correct_response", "response_choice_set", "expected_response"}
    assert audit.saved_metadata_findings(fixture, allowed) == []
    fixture["block_csv_preview"]["blocks"][0]["preview_rows"][0].pop("correct_response")
    assert audit.saved_metadata_findings(fixture, allowed) == [{
        "row_label": "Left", "family": "audio_tactile", "field": "correct_response", "affected_rows": 1}]


def test_condition_label_loss_is_separate_from_number_formatting():
    fixture = capture()
    fixture["design"]["protocol"]["block_specs"] = [{"label": "Left direction"}]
    assert audit.saved_block_label_findings(fixture)[0]["classification"] == "descriptive_label_replaced"
    fixture["design"]["protocol"]["block_specs"][0]["label"] = "Block 01"
    assert audit.saved_block_label_findings(fixture)[0]["classification"] == "number_format_only"


def test_duration_check_uses_actual_float_wav_and_rejects_historical_fallback(tmp_path):
    import soundfile
    path = tmp_path / audit.RESOURCES / "assets/short.wav"
    path.parent.mkdir(parents=True)
    # Native assets can use IEEE float; the historical four-second fallback
    # must not pass just because both inventory and captured metadata repeat it.
    with soundfile.SoundFile(path, mode="w", samplerate=8000, channels=1, subtype="FLOAT") as wav:
        wav.write([0.0] * 1001)
    fixture = capture()
    source = {"label": "short", "prebaked_path": "assets/short.wav", "duration_s": 1001 / 8000}
    fixture["design"]["noises"] = [source]
    assert audit.source_duration_checks(tmp_path, fixture)[0]["status"] == "match"
    source["duration_s"] = 4
    check = audit.source_duration_checks(tmp_path, fixture)[0]
    assert check["status"] == "mismatch"
    assert check["frames"] == 1001


@pytest.fixture
def public_inputs(tmp_path):
    """Real tiny files through the existing population owner; no native execution."""
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    root, captures = tmp_path / "source", tmp_path / "captures"
    status_path = root / audit.RESOURCES / "assets/preloads/profile_recreation_status.json"
    profiles, cases, native_cases = [], [], []
    publication = "doi:10.1234/paper"
    for name in ("passed", "guarded", "failed", "local"):
        eligible = name != "guarded"
        template = root / audit.RESOURCES / "study_templates" / f"{name}.json"
        save(template, {"id": name})
        profiles.append({"template_id": name, "runner_readiness": "ready" if eligible else "blocked_missing_parameters",
                         "profile_checks_passed": eligible, "doi": "" if name == "local" else "10.1234/paper",
                         "publication_status": "unpublished_lab_profile" if name == "local" else "published"})
        snapshot = capture()
        snapshot["design"]["study_profile_id"] = name
        if name == "passed":
            snapshot["design"]["study_profile_reference_parameters"] = {"dashboard_run_setup": {"experiment_structure": "pre_post"}}
        snapshot["design"]["protocol"]["trial_strips"] = [{"label": "Trial", "metadata": {}}]
        for row in snapshot["block_csv_preview"]["blocks"][0]["preview_rows"]:
            row["row_label"] = "Trial"
        if not eligible:
            snapshot["block_csv_preview"] = {}
            snapshot["custom_workflow"]["ready_to_prepare"] = False
        save(captures / f"{name}.json", snapshot)
        blocks = [{"index": 1, "label": "Block 1", "rows": 2}] if eligible else []
        case = {"template_id": name, "template_sha256": audit.sha256(template),
                "capture_file": f"{name}.json", "capture_sha256": audit.sha256(captures / f"{name}.json"),
                "configuration_eligible": eligible, "source_trial_count": 2 if eligible else 0,
                "source_block_rows": blocks, "page_errors": [],
                "status": "complete_plan_captured" if eligible else "blocked_as_shipped"}
        cases.append(case)
        native = {key: case[key] for key in ("template_id", "template_sha256", "capture_sha256", "source_trial_count", "source_block_rows")}
        native.update(status="failed" if name == "failed" else "blocked" if not eligible else "software_pipeline_passed",
                      participant_index=1, physical_timing_qualified=False, replication_qualified=False,
                      execution={"status": "not_run"}, error="C:\\Users\\PRIVATE_SENTINEL\\participant.csv")
        if not eligible:
            native["native_guard_error"] = "native_complete_block_plan_required"
        elif name != "failed":
            parts = [{"manifest_sha256": "a" * 64, "block_count": 1, "trial_count": 2,
                      "part_session_id": "synthetic_part_1", "part_number": 1 if name == "passed" else None,
                      "blocks": [{"trial_count": 2}], "manifest_path": "C:/PRIVATE_SENTINEL/part.json"}]
            observed = [{"package_manifest_sha256": "a" * 64, "block_count": 1, "trial_count": 2,
                         "per_block_trial_counts": [2], "stage_count": 3, "gate_count": 2,
                         "all_block_schedules_compiled": True, "all_saved_occurrences_preserved": True,
                         "all_callback_boundaries_matched": True,
                         "all_trial_response_identities_outcomes_and_rts_matched": True,
                         "scored_responses": [{"participant": "PRIVATE_SENTINEL"}]}]
            if name == "passed":
                parts.append({**copy.deepcopy(parts[0]), "manifest_sha256": "f" * 64,
                              "part_session_id": "synthetic_part_2", "part_number": 2})
                observed.append({**copy.deepcopy(observed[0]), "package_manifest_sha256": "f" * 64})
            native.update(full_plan_preserved=True, all_part_packages_verified=True, all_block_schedules_compiled=True,
                          handoff_sha256="b" * 64, parts=parts,
                          generation={"status": "premade_assets_reused"},
                          execution={"status": "completed_software", "receipt": {
                              "passed": True, "input_manifest_sha256": "b" * 64, "parts": observed,
                              "group_result_manifest": "C:/PRIVATE_SENTINEL/group.results.json" if name == "passed" else None,
                              "clock_basis": "test-only-sample-paced-simulated-monotonic", "synthetic_responses": True,
                              "physical_device_used": False, "timing_qualification": "unqualified"},
                              "independent_file_audit": {"passed": True, "scoredTrialCount": 2 * len(parts), "datasetRowCount": 2 * len(parts),
                                                         "schema": "pps.native-group-result-file-audit.v1" if name == "passed" else "pps.native-result-file-audit.v1",
                                                         "partCount": len(parts), "evidence": "file-contract-only", "timingQualification": "unqualified",
                                                         "path": "C:/PRIVATE_SENTINEL/results"}})
        native_cases.append(native)
    save(status_path, {"profiles": profiles})
    source = root / audit.ROW_CONTRACT_SOURCE
    source.parent.mkdir(parents=True)
    source.write_text("ROW_CONTRACT_FIELDS = ()\n", encoding="utf-8")
    save(root / audit.PROJECTION, {"publications": [{"networkNodeId": publication, "templateIds": ["passed", "guarded"]}],
         "studies": [{"studyRowId": publication + "::a", "networkNodeId": publication,
                      "experimentLabel": "Source task", "templateIds": ["passed", "guarded"],
                      "parameterStatusCounts": {"reported_complete": 1, "partial": 10},
                      "nativeQualification": "not_assessed", "contracts": []}]})
    input_hashes = {str(status_path.relative_to(root)).replace("\\", "/"): audit.sha256(status_path)}
    save(captures / "capture-report.json", {"schema": "pps-preset-plan-capture.v1", "captured_at": "2026-10-28", "input_hashes": input_hashes, "cases": cases})
    for case in native_cases:
        case["capture_input_hashes"] = input_hashes
    native_path, candidate_path = tmp_path / "native.json", tmp_path / "candidate.json"
    save(native_path, {"schema": "pps-native-preset-pipeline-audit.v1", "cases": native_cases,
         "all_capture_cases_selected": True, "capture_report_sha256": audit.sha256(captures / "capture-report.json"),
         "designer_test_exe_sha256": "c" * 64, "runner_test_exe_sha256": "d" * 64,
         "physical_timing_qualified": False, "replication_qualified": False})
    save(candidate_path, {"schema": "pps-native-windows-candidate.v1", "source_commit": "e" * 40,
                          "private_path": "C:/PRIVATE_SENTINEL/installer.exe"})
    return {"root": root, "captures": captures, "native_report": native_path,
            "candidate_manifest": candidate_path, "source_commit": "e" * 40,
            "ci_run_url": "https://github.com/GeorgeFejer91/pps-kit/actions/runs/123"}


def test_public_export_keeps_native_outcomes_and_science_separate(public_inputs, tmp_path):
    report = audit.build_public_report(**public_inputs)
    rows = {row["template_id"]: row for row in report["presets"]}
    assert report["counts"]["native_statuses"] == {"blocked": 1, "failed": 1, "software_pipeline_passed": 2}
    assert rows["passed"]["executed_trial_rows"] == 4
    assert rows["passed"]["executed_stages"] == 6
    assert rows["passed"]["verified_parts"] == 2
    assert rows["passed"]["source_reviews"][0]["parameter_status_counts"] == {"reported_complete": 1, "partial": 10}
    assert rows["failed"]["native_status"] == "failed"
    assert rows["failed"]["executed_trial_rows"] is None
    assert rows["failed"]["study_mapping_status"] == "publication_only"
    assert rows["failed"]["source_reviews"] == []
    assert rows["local"]["study_mapping_status"] == "local_unpublished"
    assert rows["guarded"]["native_guard_code"] == "native_complete_block_plan_required"
    assert rows["guarded"]["software_execution_verified"] is False
    assert all(row["published_protocol_equivalence"] == "not_established_by_software_audit" for row in rows.values())
    assert report["physical_timing_qualification"] == "not_assessed"
    assert "PRIVATE_SENTINEL" not in json.dumps(report)
    destination = tmp_path / "public"
    audit.write_public_report(report, destination)
    with (destination / "software-validation.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == 4
    assert csv_rows[0]["source_commit"] == "e" * 40
    assert "PRIVATE_SENTINEL" not in (destination / "software-validation.csv").read_text()
    with pytest.raises(FileExistsError):
        audit.write_public_report(report, destination)


@pytest.mark.parametrize("mutation", ["missing_case", "duplicate_case", "template_hash", "capture_hash", "capture_report_hash",
                                    "input_hash", "candidate_commit", "source_commit", "ci_url", "preflight", "false_guard",
                                    "false_pass", "result_rows", "part_hash", "physical", "source_counts", "missing_part",
                                    "capture_bytes", "template_bytes", "capture_path", "duplicate_parts", "part_identity",
                                    "part_order", "missing_group_receipt", "wrong_audit_kind", "group_part_count"])
def test_public_export_rejects_unbound_or_overstated_evidence(public_inputs, mutation):
    inputs = copy.deepcopy(public_inputs)
    native = audit.read_json(inputs["native_report"])
    case = native["cases"][0]
    if mutation == "missing_case":
        native["cases"].pop()
    elif mutation == "duplicate_case":
        native["cases"].append(case)
    elif mutation in {"template_hash", "capture_hash"}:
        case["template_sha256" if mutation == "template_hash" else "capture_sha256"] = "f" * 64
    elif mutation == "capture_report_hash":
        native["capture_report_sha256"] = "f" * 64
    elif mutation == "input_hash":
        case["capture_input_hashes"] = {}
    elif mutation == "candidate_commit":
        inputs["candidate_manifest"].write_text(json.dumps({"schema": "pps-native-windows-candidate.v1", "source_commit": "f" * 40}))
    elif mutation == "source_commit":
        inputs["source_commit"] = "C:/PRIVATE_SENTINEL"
    elif mutation == "ci_url":
        inputs["ci_run_url"] += "?token=PRIVATE_SENTINEL"
    elif mutation == "preflight":
        case["status"] = "reviewed"
    elif mutation == "false_guard":
        native["cases"][1]["native_guard_error"] = "storage_unavailable"
    elif mutation == "false_pass":
        case["execution"]["receipt"]["parts"][0]["all_callback_boundaries_matched"] = False
    elif mutation == "result_rows":
        case["execution"]["independent_file_audit"]["datasetRowCount"] = 1
    elif mutation == "part_hash":
        case["execution"]["receipt"]["parts"][0]["package_manifest_sha256"] = "f" * 64
    elif mutation == "physical":
        case["execution"]["receipt"]["physical_device_used"] = True
    elif mutation == "source_counts":
        case["source_trial_count"] = 1
    elif mutation == "missing_part":
        case["parts"].pop()
        case["execution"]["receipt"]["parts"].pop()
        case["execution"]["independent_file_audit"].update(scoredTrialCount=2, datasetRowCount=2)
    elif mutation == "duplicate_parts":
        case["parts"][1] = copy.deepcopy(case["parts"][0])
        case["execution"]["receipt"]["parts"][1] = copy.deepcopy(case["execution"]["receipt"]["parts"][0])
    elif mutation == "part_identity":
        case["parts"][1]["part_session_id"] = case["parts"][0]["part_session_id"]
    elif mutation == "part_order":
        case["parts"][1]["part_number"] = 1
    elif mutation == "missing_group_receipt":
        case["execution"]["receipt"].pop("group_result_manifest")
    elif mutation == "wrong_audit_kind":
        case["execution"]["independent_file_audit"]["schema"] = "pps.native-result-file-audit.v1"
    elif mutation == "group_part_count":
        case["execution"]["independent_file_audit"]["partCount"] = 1
    elif mutation == "capture_bytes":
        with (inputs["captures"] / "passed.json").open("a") as handle:
            handle.write(" ")
    elif mutation == "template_bytes":
        with (inputs["root"] / audit.RESOURCES / "study_templates/passed.json").open("a") as handle:
            handle.write(" ")
    elif mutation == "capture_path":
        capture_report = audit.read_json(inputs["captures"] / "capture-report.json")
        capture_report["cases"][0]["capture_file"] = "../private.json"
        (inputs["captures"] / "capture-report.json").write_text(json.dumps(capture_report), encoding="utf-8")
    inputs["native_report"].write_text(json.dumps(native), encoding="utf-8")
    with pytest.raises(ValueError):
        audit.build_public_report(**inputs)


def test_public_export_preserves_only_declared_customizations(public_inputs):
    native = audit.read_json(public_inputs["native_report"])
    native["cases"][0]["generation"] = {"status": "generated", "customized_controls": True,
        "source_algorithm": "rand-0.8.8-std-rng-box-muller.v1", "legacy_numpy_seed_compatible": False,
        "sources": [{"path": "C:/PRIVATE_SENTINEL/generated.wav"}]}
    native["cases"][0]["toolkit_iti_resolution"] = {"accepted_for_software_audit": True,
        "source_distribution_reported": False, "source_anchor_reported": False, "legacy_compatible": False,
        "private_note": "PRIVATE_SENTINEL"}
    public_inputs["native_report"].write_text(json.dumps(native), encoding="utf-8")
    result = audit.build_public_report(**public_inputs)
    row = next(row for row in result["presets"] if row["template_id"] == "passed")
    assert row["customizations"] == ["nonlegacy_native_controls", "toolkit_iti_realization"]
    assert row["source_algorithm"] == "rand-0.8.8-std-rng-box-muller.v1"
    assert "PRIVATE_SENTINEL" not in json.dumps(result)


def test_public_cli_is_opt_in_and_ordinary_audit_output_is_unchanged(public_inputs, tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", public_inputs["root"])
    arguments = [str(SCRIPT), "--captures", str(public_inputs["captures"])]
    monkeypatch.setattr("sys.argv", arguments)
    audit.main()
    ordinary = public_inputs["captures"] / "population-audit.json"
    before = ordinary.read_bytes()
    assert json.loads(before) == audit.build_report(public_inputs["root"], public_inputs["captures"])
    output = tmp_path / "public_cli"
    monkeypatch.setattr("sys.argv", arguments + ["--public-output", str(output)])
    with pytest.raises(SystemExit) as error:
        audit.main()
    assert error.value.code == 2
    assert not output.exists()
    export = ["--public-output", str(output)]
    for key in ("native_report", "candidate_manifest", "source_commit", "ci_run_url"):
        export += ["--" + key.replace("_", "-"), str(public_inputs[key])]
    monkeypatch.setattr("sys.argv", arguments + export)
    audit.main()
    assert ordinary.read_bytes() == before
    assert audit.read_json(output / "software-validation.json")["counts"]["presets"] == 4
