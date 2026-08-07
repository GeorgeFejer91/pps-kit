from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


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
    assert 'desktop_1440_light_editable_step_badges.png' in audit_source
    assert 'profile lock shackle has no distinct open visual state' in audit_source
    assert 'default immutable profile does not initialize in read-only mode' in audit_source
    assert 'read-only workflow repeats the sidebar lock state in visible step badges' in audit_source
    assert 'editable custom workflow loses its step-review badges' in audit_source
    assert 'f"{case.name}_theme_toggle.png"' in audit_source
    assert 'desktop_1440_dark_theme_toggle.png' in audit_source
    assert 'theme toggle indicator does not move between sun and moon' in audit_source
    assert 'ViewportCase("phone_390_dark", 390, 844, "dark", False)' in audit_source
    assert 'ViewportCase("phone_360_light", 360, 800, "light", False)' in audit_source
    assert 'ViewportCase("phone_320_light", 320, 800, "light", False, False)' in audit_source
    assert 'ViewportCase("phone_landscape_568_light", 568, 320, "light", False, False)' in audit_source
    assert 'ViewportCase("boundary_600_dark", 600, 900, "dark", False, False)' in audit_source
    assert 'ViewportCase("boundary_601_light", 601, 900, "light", False)' in audit_source
    assert 'ViewportCase("boundary_760_light", 760, 900, "light", False, False)' in audit_source
    assert 'ViewportCase("boundary_761_light", 761, 900, "light", False, False)' in audit_source
    assert "mobile page navigation is not above the sidebar" in audit_source
    assert "mobile section navigation is expanded before the user requests it" in audit_source
    assert "visible interactive targets are below {target_floor}x{target_floor} CSS px" in audit_source
    assert ".bounded-select-native" in audit_source
    assert "page-navigation tab labels are clipped" in audit_source
    assert "page-navigation tabs overlap" in audit_source
    assert 'for page_name in ("documentation", "downloads", "toolkit")' in audit_source
    assert "tab does not activate its page" in audit_source
    assert 'keyboard_steps = (' in audit_source
    assert 'page.keyboard.press("Shift+Tab")' in audit_source
    assert "mobile modal allows keyboard focus to escape its dialog" in audit_source
    assert "step footer is not in static document flow on phone" in audit_source
    assert "mobile table cells are not stacked as labeled card rows" in audit_source
    assert "block summary exceeds its card" in audit_source
    assert "page navigation overlaps a sticky segment heading" in audit_source
    assert 'browser_errors = list(dict.fromkeys(page_errors))' in audit_source
    assert "getComputedStyle(topbar).position === 'sticky'" in audit_source
    assert "element.offsetTop - stickyTopbarHeight - 8" in audit_source
    assert '"--page-url"' in audit_source
    assert '"--page-path"' in audit_source


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


def test_visual_layout_audit_covers_mobile_breakpoints_without_full_boundary_matrix() -> None:
    audit = _load_audit_module()
    dimensions = {(case.width, case.height) for case in audit.CASES}

    assert {
        (320, 800),
        (360, 800),
        (390, 844),
        (568, 320),
        (600, 900),
        (601, 900),
        (760, 900),
        (761, 900),
    } <= dimensions
    assert audit.ViewportCase("probe", 600, 900, "light", False, False).workflow_segment_indices == (5, 6)
    assert audit.ViewportCase("full", 390, 844, "light", False).workflow_segment_indices == tuple(range(7))


def test_visual_layout_audit_builds_direct_and_relative_page_urls() -> None:
    audit = _load_audit_module()
    phone = audit.ViewportCase("phone", 390, 844, "dark", False)
    desktop = audit.ViewportCase("desktop", 1440, 900, "light", True)

    direct = audit._page_url(
        "",
        phone,
        page_url="https://pps.example/app?existing=kept&desktop=1",
    )
    direct_parts = urlsplit(direct)
    direct_query = parse_qs(direct_parts.query)
    assert direct_parts.scheme == "https"
    assert direct_parts.netloc == "pps.example"
    assert direct_parts.path == "/app"
    assert direct_query["existing"] == ["kept"]
    assert direct_query["page"] == ["toolkit"]
    assert direct_query["forceStaticPreview"] == ["1"]
    assert direct_query["auditStaticPreview"] == ["1"]
    assert "desktop" not in direct_query

    relative = audit._page_url(
        "http://127.0.0.1:8000/root",
        desktop,
        page_path="custom/dashboard.html",
    )
    relative_parts = urlsplit(relative)
    relative_query = parse_qs(relative_parts.query)
    assert relative_parts.path == "/root/custom/dashboard.html"
    assert relative_query["desktop"] == ["1"]


def test_visual_layout_audit_rejects_phone_navigation_target_and_breakpoint_regressions() -> None:
    audit = _load_audit_module()
    phone = audit.ViewportCase("phone", 390, 844, "dark", False)
    geometry = {
        "metrics": {
            "horizontal_overflow_px": 0.0,
            "picker_card_left_delta_px": 0.0,
            "picker_card_right_delta_px": 0.0,
            "panel_picker_left_delta_px": 0.0,
            "panel_picker_right_delta_px": 0.0,
            "heading_panel_left_delta_px": 0.0,
            "select_button_height_delta_px": 0.0,
            "select_button_center_delta_px": 0.0,
            "select_button_overlap_px": 0.0,
            "topbar_visible": 1.0,
            "mobile_topbar_above_rail": 1.0,
            "mobile_rail_toggles_visible": 0.0,
            "mobile_sections_collapsed": 0.0,
            "mobile_companion_collapsed": 0.0,
            "mobile_rail_height_px": 420.0,
            "site_tab_labels_fit": 1.0,
            "site_tab_overlap_px": 0.0,
            "mode_icon_center_delta_px": 0.0,
            "mode_switch_center_delta_px": 0.0,
            "mode_view_switch_gap_px": 1.0,
            "mode_switch_edit_gap_px": 1.0,
            "mode_label_center_delta_px": 0.0,
            "resize_handles_visible": 1.0,
        },
        "primary_label_fits": True,
        "undersized_targets": [],
        "undersized_phone_targets": [{"selector": "#small", "width": 40, "height": 40}],
    }

    failures = audit.assess_geometry(phone, geometry)

    assert any("compact section and connection disclosures" in failure for failure in failures)
    assert any("expanded before" in failure for failure in failures)
    assert any("taller than 300" in failure for failure in failures)
    assert any("below 44x44" in failure for failure in failures)
    assert any("resize handles remain" in failure for failure in failures)


def test_visual_layout_audit_rejects_late_mobile_workflow_regressions() -> None:
    audit = _load_audit_module()
    phone = audit.ViewportCase("phone", 360, 800, "light", False)
    late_geometry = {
        "footer_count": 1,
        "static_footer_count": 0,
        "local_horizontal_overflow_px": 28.0,
        "card_table_count": 1,
        "card_table_unstacked_cells": 3,
        "card_table_min_font_px": 9.0,
        "block_summary_count": 1,
        "block_summary_overflow_px": 18.0,
    }

    failures = audit.assess_mobile_segment(phone, 5, late_geometry)

    assert any("static document flow" in failure for failure in failures)
    assert any("local horizontal overflow" in failure for failure in failures)
    assert any("not stacked" in failure for failure in failures)
    assert any("smaller than 12" in failure for failure in failures)
    assert any("block summary exceeds" in failure for failure in failures)
    assert audit.assess_mobile_segment(
        audit.ViewportCase("tablet", 761, 900, "light", False),
        5,
        late_geometry,
    ) == []
