from __future__ import annotations

from pathlib import Path
import base64
from unittest.mock import patch

from fastapi.testclient import TestClient

from peripersonal_space_toolkit import dashboard_app
from peripersonal_space_toolkit.dashboard_app import DashboardController, create_app
from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.profile_bundle import write_profile_bundle


def test_desktop_bootstrap_exchanges_token_for_http_only_cookie(tmp_path: Path) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller, companion_token="launch-secret", require_mutation_token=True))
    denied = client.post("/api/design", json={"participant_id": "P002"})
    assert denied.status_code == 403
    bootstrap = client.get("/api/bootstrap?token=launch-secret", follow_redirects=False)
    assert bootstrap.status_code == 302
    assert bootstrap.headers["location"].endswith("/dashboard/compiled/index.html?desktop=1")
    cookie = bootstrap.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    accepted = client.post("/api/design", json={"participant_id": "P002"})
    assert accepted.status_code == 200
    assert accepted.json()["participant_id"] == "P002"


def test_desktop_capability_contract(tmp_path: Path) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller))
    capabilities = client.get("/api/capabilities").json()
    assert capabilities["mode"] == "desktop_full"
    assert capabilities["can_render_looming"] is True
    assert capabilities["can_launch_runner"] is True
    compiled = client.get("/dashboard/compiled/index.html")
    assert compiled.status_code == 200
    assert "PPS Experiment Designer" in compiled.text


def test_segment_zero_creates_named_clean_slate_in_researcher_workspace(tmp_path: Path) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        template_dir=template_dir,
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller))

    response = client.post("/api/project/new-custom", json={"name": "Clean Slate Pilot"})

    assert response.status_code == 200
    state = response.json()
    assert state["design"]["name"] == "Clean Slate Pilot"
    assert state["design"]["study_profile_id"] == ""
    assert state["design"]["noises"] == []
    assert state["design"]["custom_looming_files"] == []
    assert state["design"]["prestimulus_files"] == []
    assert state["design"]["protocol"]["trial_strips"] == []
    assert state["design"]["protocol"]["soa_values_ms"] == []
    assert state["design"]["study_profile_reference_parameters"]["profile_status"] == "draft"
    assert state["design"]["study_profile_reference_parameters"]["created_from"] == "blank_design"
    assert state["project"]["project_kind"] == "custom"
    assert Path(state["project"]["profile_dir"]).is_dir()
    assert state["custom_workflow"]["current_step"] == "stimulus"
    assert state["custom_workflow"]["edit_step"] == "stimulus"
    assert state["custom_workflow"]["confirmed_steps"] == ["study"]
    assert state["custom_workflow"]["review_revision"] == 0
    assert state["template_directory"] == {"kind": "local", "path": str(template_dir.resolve()), "url": ""}
    with patch("peripersonal_space_toolkit.dashboard_app.subprocess.Popen") as open_process:
        opened = client.post("/api/local/open-folder", json={"path": str(template_dir)})
    assert opened.status_code == 200
    assert opened.json()["path"] == str(template_dir.resolve())
    open_process.assert_called_once()


def test_save_and_continue_is_the_durable_sequential_edit_boundary(tmp_path: Path, monkeypatch) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        template_dir=tmp_path / "templates",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller))
    state = client.post("/api/project/new-custom", json={"name": "Sequential Pilot"}).json()
    project_id = state["project"]["project_id"]

    changed_design = state["design"]
    changed_design["trajectory"]["padding_pre_s"] = 0.75
    incomplete = client.post(
        "/api/design",
        json={
            "design": changed_design,
            "workflow_action": {
                "type": "save_and_continue",
                "step_id": "stimulus",
                "expected_revision": 0,
            },
        },
    )
    assert incomplete.status_code == 200
    incomplete_state = incomplete.json()
    assert incomplete_state["workflow_action_result"]["advanced"] is False
    assert incomplete_state["custom_workflow"]["edit_step"] == "stimulus"
    assert incomplete_state["custom_workflow"]["review_revision"] == 1
    assert incomplete_state["design"]["trajectory"]["padding_pre_s"] == 0.75

    monkeypatch.setattr(dashboard_app, "_custom_stimulus_missing", lambda *_args, **_kwargs: [])
    saved = client.post(
        "/api/design",
        json={
            "design": incomplete_state["design"],
            "workflow_action": {
                "type": "save_and_continue",
                "step_id": "stimulus",
                "expected_revision": 1,
            },
        },
    )
    assert saved.status_code == 200
    saved_state = saved.json()
    assert saved_state["workflow_action_result"] == {
        "type": "save_and_continue",
        "saved_step": "stimulus",
        "unlocked_step": "trials",
        "advanced": True,
        "missing": [],
    }
    assert saved_state["custom_workflow"]["edit_step"] == "trials"
    assert saved_state["custom_workflow"]["confirmed_steps"] == ["study", "stimulus"]
    assert saved_state["custom_workflow"]["review_revision"] == 2

    reopened_project = client.post(f"/api/projects/{project_id}/load").json()
    assert reopened_project["custom_workflow"]["edit_step"] == "trials"
    assert reopened_project["custom_workflow"]["confirmed_steps"] == ["study", "stimulus"]

    skipped = client.post(
        "/api/design",
        json={
            "workflow_action": {
                "type": "save_and_continue",
                "step_id": "baseline",
                "expected_revision": 2,
            },
        },
    )
    assert skipped.status_code == 400
    assert "Save trials before continuing" in skipped.json()["detail"]


def test_reopening_saved_segment_marks_later_confirmations_for_review(tmp_path: Path, monkeypatch) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        template_dir=tmp_path / "templates",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller))
    state = client.post("/api/project/new-custom", json={"name": "Reopen Pilot"}).json()
    monkeypatch.setattr(dashboard_app, "_custom_stimulus_missing", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dashboard_app, "_custom_trials_missing", lambda *_args, **_kwargs: [])

    for revision, step_id in enumerate(("stimulus", "trials")):
        response = client.post(
            "/api/design",
            json={
                "design": state["design"],
                "workflow_action": {
                    "type": "save_and_continue",
                    "step_id": step_id,
                    "expected_revision": revision,
                },
            },
        )
        assert response.status_code == 200
        state = response.json()

    assert state["custom_workflow"]["edit_step"] == "baseline"
    reopened = client.post(
        "/api/design",
        json={
            "workflow_action": {
                "type": "reopen",
                "step_id": "stimulus",
                "expected_revision": 2,
            },
        },
    )
    assert reopened.status_code == 200
    workflow = reopened.json()["custom_workflow"]
    assert workflow["edit_step"] == "stimulus"
    assert workflow["confirmed_steps"] == ["study"]
    assert workflow["needs_review_steps"] == ["trials"]
    decision_states = {step["id"]: step["decision_state"] for step in workflow["steps"]}
    assert decision_states["stimulus"] == "editing"
    assert decision_states["trials"] == "needs_review"
    assert decision_states["baseline"] == "locked"


def test_finalized_custom_profile_rejects_direct_full_design_mutation(tmp_path: Path) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        template_dir=tmp_path / "templates",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller))
    state = client.post("/api/project/new-custom", json={"name": "Finalized Guard"}).json()
    finalized_design = state["design"]
    finalized_design["study_profile_reference_parameters"]["profile_status"] = "finalized"
    finalized = client.post("/api/design", json={"design": finalized_design})
    assert finalized.status_code == 200
    assert finalized.json()["design"]["study_profile_reference_parameters"]["profile_status"] == "draft"

    with controller._lock:
        controller.design.study_profile_reference_parameters["profile_status"] = "finalized"
    mutated_design = controller.snapshot()["design"]
    mutated_design["name"] = "Bypassed mutation"
    rejected = client.post("/api/design", json={"design": mutated_design})
    assert rejected.status_code == 400
    assert "read-only" in rejected.json()["detail"]

    artifact_rejected = client.post("/api/block-csv/edit")
    assert artifact_rejected.status_code == 400
    assert "read-only" in artifact_rejected.json()["detail"]


def test_profile_finalization_requires_completed_sequential_review(tmp_path: Path) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        template_dir=tmp_path / "templates",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    client = TestClient(create_app(controller))
    client.post("/api/project/new-custom", json={"name": "Review Gate"})

    missing_revision = client.post("/api/profiles/save-prepared", json={"name": "Blocked"})
    assert missing_revision.status_code == 400
    assert "revision" in missing_revision.json()["detail"]

    incomplete = client.post(
        "/api/profiles/save-prepared",
        json={"name": "Blocked", "expected_revision": 0},
    )
    assert incomplete.status_code == 400
    assert "Sequential review is incomplete" in incomplete.json()["detail"]


def test_desktop_import_registers_verified_bundle_as_custom_draft(tmp_path: Path) -> None:
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "registry",
    )
    bundle = write_profile_bundle(
        default_design(), tmp_path / "portable.pps-profile", profile_id="portable", display_name="Portable profile"
    )
    client = TestClient(create_app(controller))
    response = client.post(
        "/api/profiles/import-bundle",
        json={"content_base64": base64.b64encode(bundle.read_bytes()).decode("ascii")},
    )
    assert response.status_code == 200
    state = response.json()
    assert state["project"]["project_kind"] == "custom"
    assert state["custom_workflow"]["is_custom"] is True
    assert state["custom_workflow"]["is_finalized"] is False
    assert Path(state["profile_bundle_import"]["bundle_path"]).is_file()
