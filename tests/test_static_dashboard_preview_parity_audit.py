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
    assert "prepareButton.disabled = staticModeActive ||" in app_js
    assert "button.disabled = !readonly || staticModeActive" in app_js
    assert "mutating_enabled" in app_js


def test_static_dashboard_preview_parity_audit_targets_all_previewable_profiles():
    module = _load_audit_module()

    inventory = module._load_preload_inventory()
    status = module.load_profile_recreation_status(module.REPO_ROOT)
    all_ids = module._target_template_ids(inventory, status, profile_set="all")
    ready_ids = module._target_template_ids(inventory, status, profile_set="ready-all")

    assert len(all_ids) == 24
    assert ready_ids == [
        "study5_box_breathing_pps",
        "roussel_2025_dynaspace_mobile_pps",
        "matsuda_2021_four_directions",
        "barumerli_2026_arm_movement_exp1",
        "barumerli_2026_arm_movement_exp2",
        "noel_2015_bodily_self",
        "noel_2015_bodily_self_back_space",
        "pfeiffer_2018_lateral_perihead_left_to_right",
        "study5_dynaspace_lateral_45_pps",
        "serino_2015_peri_hand_exp3",
        "serino_2015_peri_trunk_exp1",
    ]
    assert module.dashboard_audit_url("https://georgefejer91.github.io/pps-kit/") == (
        "https://georgefejer91.github.io/pps-kit/src/peripersonal_space_toolkit/dashboard/index.html"
        "?page=toolkit&forceStaticPreview=1&auditStaticPreview=1"
    )
