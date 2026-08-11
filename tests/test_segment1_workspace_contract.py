from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "src" / "peripersonal_space_toolkit" / "dashboard"
VIEWER = ROOT / "src" / "peripersonal_space_toolkit" / "viewer" / "trajectory-viewer.js"


def _sources() -> tuple[str, str, str, str]:
    return (
        (DASHBOARD / "index.html").read_text(encoding="utf-8"),
        (DASHBOARD / "styles.css").read_text(encoding="utf-8"),
        (DASHBOARD / "app.js").read_text(encoding="utf-8"),
        VIEWER.read_text(encoding="utf-8"),
    )


def test_segment1_is_one_source_first_workspace_with_grouped_inventory() -> None:
    html, styles, app_js, _viewer_js = _sources()

    assert html.count('data-step-panel="stimulus"') == 1
    assert html.index("Stimulus Type Selection") < html.index('class="stimulus-editor-grid"')
    assert html.index('class="stimulus-editor-grid"') < html.index('class="bake-action-row stimulus-commit-row"')
    assert html.index('class="bake-action-row stimulus-commit-row"') < html.index('id="stimulus-pool"')
    assert "Looming / spatialized stimuli" in html
    assert "Fixed audio clips" in html
    assert 'id="new-ingredient"' in html
    assert 'id="bake-label"' in html and "required" in html[html.index('id="bake-label"'):html.index('id="bake-label"') + 160]
    assert 'id="fixed-clip-trajectory-note"' in html
    assert "Preserved audio clip — no trajectory" in html
    assert ".fixed-clip-trajectory-note[hidden]" in styles
    assert ".source-mode-row[hidden]" in styles
    assert ".stimulus-editor-grid" in styles
    assert "grid-template-columns: minmax(360px" in styles
    assert "@media (max-width: 1180px)" in styles
    assert "function selectIngredient" in app_js
    assert "ingredientEditorDirty" in app_js
    assert "confirmDiscardIngredientDraft" in app_js
    assert 'button.textContent = remake ? (isFixed ? "Update Clip" : "Remake Stimulus")' in app_js


def test_manual_audio_colour_overlay_accepts_visual_and_hex_input() -> None:
    html, styles, app_js, _viewer_js = _sources()

    assert 'id="audio-color-modal"' in html
    assert 'role="dialog" aria-modal="true"' in html
    assert 'id="audio-color-native" type="color"' in html
    assert 'id="audio-color-hex" type="text"' in html
    assert 'pattern="#[0-9A-Fa-f]{6}"' in html
    assert 'id="audio-color-apply"' in html
    assert 'id="audio-color-cancel"' in html
    assert "function normalizeDisplayColorHex" in app_js
    assert "function openAudioColorModal" in app_js
    assert "function applyAudioColorModal" in app_js
    assert "function trapModalFocus" in app_js
    assert ".visual-color-picker" in styles
    assert '.visual-color-picker input[type="color"]' in styles
    assert '"@chenglou/pretext": "./node_modules/@chenglou/pretext/dist/layout.js"' in html


def test_inventory_selection_and_viewer_path_selection_are_bidirectional() -> None:
    html, styles, app_js, viewer_js = _sources()

    assert 'id="noise-list"' in html and 'id="audio-list"' in html
    assert "data-select-ingredient" in app_js
    assert "data-preview-source-label" in app_js
    assert 'data.type === "pps-source-trajectory-select"' in app_js
    assert "active_source_label: selectedIngredientLabel" in app_js
    assert ".stimulus-inventory-card.selected" in styles
    assert ".stimulus-workspace-panel.profile-readonly .stimulus-preview-panel iframe" in styles
    assert "sourceTrajectoryHitTargets" in viewer_js
    assert "contrastSourceColor" in viewer_js
    assert "SOURCE_TRAJECTORY_OFFSET_M" in viewer_js
    assert 'type: "pps-source-trajectory-select"' in viewer_js
    assert "pointerMoved" in viewer_js
    assert "opacity: active ? 1 : muted ? 0.22" in viewer_js
    assert "Preserved audio clip — no trajectory" in viewer_js


def test_compiled_segment1_workspace_matches_source_contract() -> None:
    source_html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    compiled_html = (DASHBOARD / "compiled" / "index.html").read_text(encoding="utf-8")
    compiled_assets = DASHBOARD / "compiled" / "assets"
    compiled_js = "\n".join(path.read_text(encoding="utf-8") for path in compiled_assets.glob("index-*.js"))
    compiled_css = "\n".join(path.read_text(encoding="utf-8") for path in compiled_assets.glob("index-*.css"))

    assert "Stimulus and Trajectory Workspace" in source_html and "Stimulus and Trajectory Workspace" in compiled_html
    assert 'id="audio-color-modal"' in compiled_html
    assert "Remake Stimulus" in compiled_js
    assert "pps-source-trajectory-select" in compiled_js
    assert ".stimulus-editor-grid" in compiled_css
    versions = set(re.findall(r"(?:styles\.css|app\.js|designer_main\.js)\?v=([\w.-]+)", source_html))
    assert versions == {"20260811-segment1-workspace"}
