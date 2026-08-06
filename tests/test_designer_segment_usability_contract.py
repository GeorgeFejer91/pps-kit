from importlib.resources import files


def _dashboard_sources() -> tuple[str, str, str]:
    dashboard = files("peripersonal_space_toolkit.dashboard")
    return (
        dashboard.joinpath("index.html").read_text(encoding="utf-8"),
        dashboard.joinpath("app.js").read_text(encoding="utf-8"),
        dashboard.joinpath("styles.css").read_text(encoding="utf-8"),
    )


def test_segments_expose_one_clear_decision_model_each():
    html, app_js, styles = _dashboard_sources()

    assert 'id="stimulus-mode-2d"' not in html
    assert html.count('data-preview-mode="2d"') == 1
    assert "Calibration reference and safety ceiling" in html

    assert 'class="sequence-grammar"' in html
    assert "filmstrip-row-expression" in app_js
    assert "stripPreviewVariants(strip).length" in app_js
    assert "Add first trial family" in app_js

    assert 'type="radio" name="baseline-option" value="min_max"' in html
    assert 'id="include-catch-trials"' in html
    assert 'id="include-auditory-only-trials"' in html
    assert "Tactile channel 3" in app_js

    assert "Set all trial groups to" in html
    assert "Advanced file-level overrides" in app_js
    assert "Half-step repetitions add balanced extra trials deterministically" in html

    assert "Generate Blocks" in html
    assert 'id="block-order-policy-summary"' in html
    assert "randomization_strategy" in app_js
    assert "randomization_seed" in app_js

    assert 'id="profile-validation-checklist"' in html
    assert "Example orders to preview" in html
    assert '<th>Example</th>' in html
    assert "Done — Lock Profile" in html
    assert "bundleButton.hidden = !finalized" in app_js
    assert 'id="prepare-experiment" type="button" class="state-only" hidden' in html
    assert 'id="export-output-folder" type="button" class="state-only" hidden' in html

    assert ".profile-validation-checklist" in styles
    assert ".decision-summary-strip" in styles
    assert ".sequence-event-add-symbol.with-label" in styles


def test_for_ai_contract_uses_profile_finalization_boundary():
    contract = files("peripersonal_space_toolkit.dashboard").joinpath("index.html")
    repo_root = contract.parent.parent.parent.parent
    segment_contract = (repo_root / "For-AI" / "segment_registry_contract.md").read_text(encoding="utf-8")
    skill = (repo_root / "For-AI" / "skills" / "html-dashboard-orchestrator" / "SKILL.md").read_text(encoding="utf-8")

    for text in (segment_contract, skill):
        assert "Segment 6: Profile Validation and Save" in text or "Segment 6 Profile Validation and Save" in text
        assert "actual participant" in text
        assert "Runner" in text
