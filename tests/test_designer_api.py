from __future__ import annotations

from pathlib import Path
import base64

from fastapi.testclient import TestClient

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
