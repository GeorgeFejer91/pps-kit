from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "validation_protocols" / "scripts" / "run_designer_visual_layout_audit.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("run_designer_visual_layout_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_designer_layout_uses_shared_grid_and_control_tokens() -> None:
    css = (ROOT / "src" / "peripersonal_space_toolkit" / "dashboard" / "styles.css").read_text(encoding="utf-8")
    memory = (ROOT / "For-AI" / "interface_design_principles.md").read_text(encoding="utf-8")
    audit_source = SCRIPT.read_text(encoding="utf-8")

    for contract in [
        "--space-1: 4px",
        "--space-2: 8px",
        "--space-4: 16px",
        "--control-height: 36px",
        "--panel-padding: 16px",
        "height: var(--control-height)",
        "padding: var(--space-2) calc(var(--panel-padding) + 1px)",
        ".bounded-select-menu",
        ".bounded-select-button",
    ]:
        assert contract in css
    assert "Mandatory Visual Validation Loop" in memory
    assert "run_designer_visual_layout_audit.py" in memory
    assert 'step_link.click()' in audit_source
    assert 'page.locator(".decision-segment").nth(segment_index)' in audit_source
    assert 'html{scroll-behavior:auto!important}' in audit_source
    assert 'select_menu_width_delta_px' in audit_source
    assert 'f"{case.name}_segment0_dropdown.png"' in audit_source
    assert 'desktop_1440_light_profile_lock_closed.png' in audit_source
    assert 'desktop_1440_light_profile_lock_open.png' in audit_source
    assert 'desktop_1440_light_profile_copy_prompt.png' in audit_source
    assert 'profile lock shackle has no distinct open visual state' in audit_source
    assert 'f"{case.name}_theme_toggle.png"' in audit_source
    assert 'desktop_1440_dark_theme_toggle.png' in audit_source
    assert 'theme toggle indicator does not move between sun and moon' in audit_source
    assert 'ViewportCase("phone_390_dark", 390, 844, "dark", False)' in audit_source
    assert 'ViewportCase("phone_360_light", 360, 800, "light", False)' in audit_source
    assert 'ViewportCase("boundary_601_light", 601, 900, "light", False)' in audit_source
    assert "mobile page navigation is not above the sidebar" in audit_source
    assert "page-navigation tab labels are clipped" in audit_source
    assert "page-navigation tabs overlap" in audit_source
    assert 'for page_name in ("documentation", "downloads", "toolkit")' in audit_source
    assert "tab does not activate its page" in audit_source
    assert "page navigation overlaps a sticky segment heading" in audit_source


def test_visual_layout_audit_rejects_geometry_regressions() -> None:
    audit = _load_audit_module()
    case = audit.ViewportCase("test", 1440, 900, "light", True)
    geometry = {
        "metrics": {
            "horizontal_overflow_px": 4.0,
            "picker_card_left_delta_px": 0.0,
            "picker_card_right_delta_px": 0.0,
            "panel_picker_left_delta_px": 0.0,
            "panel_picker_right_delta_px": 0.0,
            "heading_panel_left_delta_px": 3.0,
            "select_button_height_delta_px": 2.0,
            "select_button_center_delta_px": 2.0,
            "select_button_overlap_px": 0.0,
            "select_menu_width_delta_px": 2.0,
            "select_menu_left_delta_px": 2.0,
            "select_menu_viewport_overflow_px": 2.0,
            "topbar_visible": 1.0,
            "mobile_topbar_above_rail": 0.0,
            "site_tab_labels_fit": 0.0,
            "site_tab_overlap_px": 2.0,
            "mode_icon_center_delta_px": 2.0,
            "mode_switch_center_delta_px": 2.0,
            "mode_view_switch_gap_px": -1.0,
            "mode_switch_edit_gap_px": -1.0,
            "mode_label_center_delta_px": 2.0,
        },
        "primary_label_fits": True,
        "undersized_targets": [],
    }

    failures = audit.assess_geometry(case, geometry)
    phone_failures = audit.assess_geometry(
        audit.ViewportCase("phone", 390, 844, "dark", False),
        geometry,
    )

    assert any("horizontal overflow" in failure for failure in failures)
    assert any("leading meridian" in failure for failure in failures)
    assert any("different heights" in failure for failure in failures)
    assert any("vertical centers" in failure for failure in failures)
    assert any("same width" in failure for failure in failures)
    assert any("anchored" in failure for failure in failures)
    assert any("extends beyond" in failure for failure in failures)
    assert any("redundant hosted top bar" in failure for failure in failures)
    assert any("sidebar meridian" in failure for failure in failures)
    assert any("overlap" in failure for failure in failures)
    assert any("horizontal centerline" in failure for failure in failures)
    assert any("mobile page navigation is not above the sidebar" in failure for failure in phone_failures)
    assert any("tab labels are clipped" in failure for failure in failures)
    assert any("tabs overlap" in failure for failure in failures)
