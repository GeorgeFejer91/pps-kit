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
    ]:
        assert contract in css
    assert "Mandatory Visual Validation Loop" in memory
    assert "run_designer_visual_layout_audit.py" in memory
    assert 'step_link.click()' in audit_source
    assert 'page.locator(".decision-segment").nth(segment_index)' in audit_source
    assert 'html{scroll-behavior:auto!important}' in audit_source


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
        },
        "primary_label_fits": True,
        "undersized_targets": [],
    }

    failures = audit.assess_geometry(case, geometry)

    assert any("horizontal overflow" in failure for failure in failures)
    assert any("leading meridian" in failure for failure in failures)
    assert any("different heights" in failure for failure in failures)
    assert any("vertical centers" in failure for failure in failures)
