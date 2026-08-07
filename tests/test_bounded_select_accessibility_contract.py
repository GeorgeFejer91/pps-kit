from __future__ import annotations

from pathlib import Path


APP_JS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "peripersonal_space_toolkit"
    / "dashboard"
    / "app.js"
).read_text(encoding="utf-8")


def test_bounded_select_tab_navigation_excludes_the_hidden_native_select() -> None:
    assert 'select.setAttribute("aria-hidden", "true")' in APP_JS
    assert "select.tabIndex = -1" in APP_JS
    assert 'event.key === "Tab"' in APP_JS
    assert "moveFocusFromBoundedSelect(event.shiftKey)" in APP_JS
    assert "element.tabIndex >= 0" in APP_JS
    assert "!element.closest('[inert], [aria-hidden=\"true\"]')" in APP_JS


def test_bounded_select_navigation_and_typeahead_share_enabled_options() -> None:
    assert "function isBoundedSelectOptionDisabled(option)" in APP_JS
    assert 'option.parentElement?.tagName === "OPTGROUP" && option.parentElement.disabled' in APP_JS
    assert "function enabledBoundedSelectItems()" in APP_JS
    assert '[data-bounded-option-index]:not([aria-disabled="true"])' in APP_JS
    assert "const enabled = enabledBoundedSelectItems();" in APP_JS
    assert "const items = enabledBoundedSelectItems();" in APP_JS
    assert "const optionDisabled = isBoundedSelectOptionDisabled(option);" in APP_JS
    assert 'item.setAttribute("aria-disabled", "true")' in APP_JS
