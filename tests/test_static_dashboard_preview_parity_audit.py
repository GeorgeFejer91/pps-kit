from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_audit_module():
    script_path = REPO_ROOT / "validation_protocols" / "scripts" / "run_static_dashboard_preview_parity_audit.py"
    spec = importlib.util.spec_from_file_location("static_dashboard_preview_parity_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_dashboard_static_preview_audit_hook_is_query_gated():
    app_js = (REPO_ROOT / "src" / "peripersonal_space_toolkit" / "dashboard" / "app.js").read_text(encoding="utf-8")

    assert "pps-static-dashboard-preview-audit-snapshot.v1" in app_js
    assert "auditStaticPreview" in app_js
    assert "forceStaticPreview" in app_js
    assert "window.PPSDashboardAudit" in app_js
    assert "function exposeDashboardAuditHook" in app_js
    assert "if (!staticPreviewAuditEnabled()) return;" in app_js
    assert "prepareButton.disabled = true;" in app_js
    assert "prepareButton.hidden = true;" in app_js
    assert "function renderCapabilityLocks()" in app_js
    assert "mutating_enabled" in app_js


def test_static_dashboard_preview_parity_audit_targets_all_previewable_profiles():
    module = _load_audit_module()

    inventory = module._load_preload_inventory()
    status = module.load_profile_recreation_status(module.REPO_ROOT)
    all_ids = module._target_template_ids(inventory, status, profile_set="all")
    ready_ids = module._target_template_ids(inventory, status, profile_set="ready-all")

    assert len(all_ids) == 30
    assert len(ready_ids) == 24
    assert ready_ids[0] == "study5_box_breathing_pps"
    assert {
        "study5_dynaspace_lateral_45_pps",
        "noel_2015_walking_full_body_action",
        "canzoneri_2013_amputation_prosthesis",
        "serino_2015_toolless_sync_training",
    }.issubset(ready_ids)
    assert set(ready_ids).issubset(all_ids)
    assert "edit-mode-button" not in module.COMPANION_REQUIRED_CONTROL_IDS
    assert "save-study-profile" not in module.COMPANION_REQUIRED_CONTROL_IDS
    assert "bake-stimulus" in module.COMPANION_REQUIRED_CONTROL_IDS
    assert module.dashboard_audit_url("https://georgefejer91.github.io/pps-kit/") == (
        "https://georgefejer91.github.io/pps-kit/src/peripersonal_space_toolkit/dashboard/index.html"
        "?page=toolkit&forceStaticPreview=1&auditStaticPreview=1"
    )
