from __future__ import annotations

from pathlib import Path
import re


APP_JS = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "designer"
    / "frontend"
    / "app.js"
).read_text(encoding="utf-8")


def test_keyboard_section_navigation_moves_focus_before_closing_mobile_disclosure() -> None:
    assert "function mobileSectionsDisclosureOpen()" in APP_JS
    assert 'window.matchMedia("(max-width: 760px)").matches' in APP_JS
    assert 'classList.contains("mobile-sections-open")' in APP_JS
    assert "if (!options.preserveMobileDisclosures) closeMobileRailDisclosures();" in APP_JS
    assert APP_JS.count("preserveMobileDisclosures: fromMobileSections") == 2
    assert APP_JS.count("const moveFocus = fromMobileSections && event.detail === 0;") == 2
    assert APP_JS.count("if (moveFocus) focusSectionNavigationTarget(") == 2
    assert "closeMobileRailDisclosures();\n        target.scrollIntoView" in APP_JS
    assert re.search(r"closeMobileRailDisclosures\(\);\s+scrollToStep\(stepId\);", APP_JS)


def test_temporary_section_focus_target_does_not_join_the_tab_order() -> None:
    assert "function focusSectionNavigationTarget(target)" in APP_JS
    assert 'const originalTabIndex = target.getAttribute("tabindex");' in APP_JS
    assert "if (originalTabIndex === null) target.tabIndex = -1;" in APP_JS
    assert "target.focus({ preventScroll: true });" in APP_JS
    assert 'target.addEventListener("blur", () => target.removeAttribute("tabindex"), { once: true });' in APP_JS
