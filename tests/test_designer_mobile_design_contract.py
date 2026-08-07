from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "src" / "peripersonal_space_toolkit" / "dashboard"


class _Markup(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def by_id(self, element_id: str) -> tuple[str, dict[str, str | None]]:
        return next(element for element in self.elements if element[1].get("id") == element_id)

    def with_role(self, role: str) -> list[tuple[str, dict[str, str | None]]]:
        return [element for element in self.elements if element[1].get("role") == role]


def _read_sources() -> tuple[str, str, str, str]:
    return tuple(
        (DASHBOARD / name).read_text(encoding="utf-8")
        for name in ("index.html", "styles.css", "app.js", "designer_main.js")
    )


def _read_compiled() -> tuple[str, str, str]:
    html = (DASHBOARD / "compiled" / "index.html").read_text(encoding="utf-8")

    def asset(suffix: str) -> str:
        match = re.search(rf'(?:src|href)="\./assets/([^"?]+\.{suffix})"', html)
        assert match, f"compiled index does not reference a {suffix} asset"
        path = DASHBOARD / "compiled" / "assets" / match.group(1)
        assert path.is_file(), f"compiled asset is missing: {path.name}"
        return path.read_text(encoding="utf-8")

    return html, asset("css"), asset("js")


def _at_rule_blocks(css: str, header: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    while (start := css.find(header, cursor)) >= 0:
        opening = css.find("{", start + len(header))
        assert opening >= 0
        depth = 0
        for index in range(opening, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(css[start:index + 1])
                    cursor = index + 1
                    break
        else:
            raise AssertionError(f"unterminated CSS block: {header}")
    return blocks


def _rule_has(css: str, selector_pattern: str, declaration_pattern: str) -> bool:
    pattern = rf"{selector_pattern}\s*\{{(?P<body>[^{{}}]*)\}}"
    return any(
        re.search(declaration_pattern, match.group("body"))
        for match in re.finditer(pattern, css, flags=re.S)
    )


def _selector_has(css: str, selector: str, declaration_pattern: str) -> bool:
    return any(
        selector in selectors and re.search(declaration_pattern, declarations)
        for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css, flags=re.S)
    )


def _compact_css(css: str) -> str:
    return re.sub(r"\s*([:;,{}])\s*", r"\1", css)


def _body_starts_with_skip_link(html: str) -> bool:
    body = re.search(r"<body[^>]*>(?P<body>.*)</body>", html, flags=re.S)
    assert body
    return bool(
        re.match(
            r'\s*<a\b(?=[^>]*\bclass="skip-link")(?=[^>]*\bhref="#main-content")[^>]*>',
            body.group("body"),
        )
    )


def test_mobile_landmarks_and_tabs_are_semantic_in_source_and_compiled() -> None:
    source_html, _styles, app_js, _designer_main = _read_sources()
    compiled_html, _compiled_css, compiled_js = _read_compiled()

    for html in (source_html, compiled_html):
        markup = _Markup(html)
        assert _body_starts_with_skip_link(html)
        main_tag, main_attrs = markup.by_id("main-content")
        assert main_tag == "main"
        assert main_attrs["tabindex"] == "-1"
        assert "workspace" in (main_attrs["class"] or "").split()
        assert '<h1 class="visually-hidden">PPS Experiment Designer</h1>' in html
        assert html.index('<h1 class="visually-hidden">') < html.index("decision-segment")

        tablists = markup.with_role("tablist")
        assert len(tablists) == 1
        tabs = markup.with_role("tab")
        assert [attrs["id"] for _tag, attrs in tabs] == [
            "page-tab-toolkit",
            "page-tab-documentation",
            "page-tab-downloads",
        ]
        for page in ("toolkit", "documentation", "downloads"):
            _tag, tab = markup.by_id(f"page-tab-{page}")
            _panel_tag, panel = markup.by_id(f"{page}-page")
            assert tab["aria-controls"] == f"{page}-page"
            assert panel["role"] == "tabpanel"
            assert panel["aria-labelledby"] == f"page-tab-{page}"
        assert markup.by_id("page-tab-toolkit")[1]["aria-selected"] == "true"
        for page in ("documentation", "downloads"):
            attrs = markup.by_id(f"page-tab-{page}")[1]
            assert attrs["aria-selected"] == "false"
            assert attrs["tabindex"] == "-1"

    for contract in (
        'button.setAttribute("aria-selected", String(active))',
        "button.tabIndex = active ? 0 : -1",
        "ArrowLeft",
        "ArrowRight",
        'event.key === "Home"',
        'event.key === "End"',
        "next.focus()",
    ):
        assert contract in app_js
    for compiled_contract in (
        "aria-selected",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
    ):
        assert compiled_contract in compiled_js


def test_mobile_rail_disclosures_are_compact_and_mutually_exclusive() -> None:
    source_html, styles, app_js, _designer_main = _read_sources()
    compiled_html, compiled_css, compiled_js = _read_compiled()

    for html in (source_html, compiled_html):
        markup = _Markup(html)
        sections = markup.by_id("mobile-rail-nav-toggle")[1]
        companion = markup.by_id("mobile-companion-toggle")[1]
        assert sections["aria-expanded"] == "false"
        assert set((sections["aria-controls"] or "").split()) == {
            "toolkit-workflow-nav",
            "documentation-section-nav",
            "download-section-nav",
        }
        assert companion["aria-expanded"] == "false"
        assert companion["aria-controls"] == "companion-panel"
        assert markup.by_id("mobile-rail-nav-current")[0] == "strong"

    mobile_css = "\n".join(_at_rule_blocks(styles, "@media (max-width: 760px)"))
    for contract in (
        ".rail .rail-nav-group",
        ".rail .companion-panel",
        "display: none",
        ".rail.mobile-sections-open .rail-nav-group.active",
        ".rail.mobile-companion-open .companion-panel",
    ):
        assert contract in mobile_css
    for contract in (
        'toggleMobileRailDisclosure("sections")',
        'toggleMobileRailDisclosure("companion")',
        'rail.classList.remove("mobile-sections-open", "mobile-companion-open")',
        "rail.classList.remove(otherClass)",
        'otherToggle?.setAttribute("aria-expanded", "false")',
        "syncMobileRailSummary()",
    ):
        assert contract in app_js
    for contract in (
        "mobile-rail-nav-toggle",
        "mobile-companion-toggle",
        "mobile-sections-open",
        "mobile-companion-open",
    ):
        assert contract in compiled_html + compiled_css + compiled_js


def test_phone_css_is_content_first_and_uses_touch_sized_static_controls() -> None:
    _html, styles, app_js, _designer_main = _read_sources()
    _compiled_html, compiled_css, compiled_js = _read_compiled()
    mobile_css = "\n".join(_at_rule_blocks(styles, "@media (max-width: 760px)"))
    compact_compiled_css = _compact_css(compiled_css)

    assert "--control-height: 44px" in mobile_css
    assert _rule_has(mobile_css, r"button,[^{]+", r"min-height:\s*44px")
    assert _rule_has(mobile_css, r"\.icon-action", r"(?:width|min-width):\s*44px")
    assert _rule_has(mobile_css, r"\.topbar", r"position:\s*sticky")
    assert _rule_has(mobile_css, r"\.rail", r"position:\s*static")
    assert _rule_has(mobile_css, r"\.workspace", r"margin-left:\s*0")
    assert _rule_has(mobile_css, r"\.segment-heading", r"position:\s*static")
    assert _rule_has(mobile_css, r"\.step-footer,[^{]+", r"position:\s*static")
    assert _rule_has(mobile_css, r"\.rail \.rail-nav-group,[^{]+", r"display:\s*none")

    landscape_css = "\n".join(
        _at_rule_blocks(
            styles,
            "@media (min-width: 480px) and (max-width: 760px) and (max-height: 500px) and (orientation: landscape)",
        )
    )
    assert _rule_has(
        landscape_css,
        r"\.topbar",
        r"grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto",
    )

    narrow_css = "\n".join(_at_rule_blocks(styles, "@media (max-width: 760px)"))
    assert _rule_has(narrow_css, r"\.panel-resize-handle", r"display:\s*none\s*!important")
    assert 'window.matchMedia("(max-width: 760px)").matches' in app_js
    assert 'panel.querySelector(":scope > .panel-resize-handle")?.remove()' in app_js
    assert 'window.matchMedia("(max-width: 760px)").addEventListener("change"' in app_js

    for contract in (
        "--control-height:44px",
        ".segment-heading{position:static",
        ".panel-resize-handle{display:none!important}",
        ".rail .rail-nav-group,.rail .companion-panel,.rail-note{display:none}",
    ):
        assert contract in compact_compiled_css
    assert "(max-width: 760px)" in compiled_js
    assert "panel-resize-handle" in compiled_js


def test_mobile_tables_are_cardized_labeled_and_progressively_revealed() -> None:
    source_html, styles, app_js, _designer_main = _read_sources()
    compiled_html, compiled_css, compiled_js = _read_compiled()
    mobile_css = "\n".join(_at_rule_blocks(styles, "@media (max-width: 760px)"))

    for html in (source_html, compiled_html):
        run_table = _Markup(html).by_id("run-sequence-table")[1]
        assert "mobile-card-table" in (run_table["class"] or "").split()
    assert app_js.count("mobile-card-table") >= 3
    assert app_js.count("data-label=") >= 8
    assert "cell.dataset.label = labels[index] || humanize(key)" in app_js
    assert 'data-mobile-table-toggle="${tableId}"' in app_js
    assert 'mobileTableToggle.setAttribute("aria-expanded", String(expanded))' in app_js
    assert '"Show first 6 rows"' in app_js
    assert _rule_has(mobile_css, r"table\.mobile-card-table td::before", r"content:\s*attr\(data-label\)")
    assert _rule_has(mobile_css, r"\.block-preview-table tbody tr:nth-child\(n \+ 7\)", r"display:\s*none")
    assert _rule_has(mobile_css, r"\.block-preview-table\.mobile-show-all tbody tr", r"display:\s*block")

    for contract in ("mobile-card-table", "data-label", "data-mobile-table-toggle", "Show first 6 rows"):
        assert contract in compiled_js
    assert "mobile-card-table" in compiled_html
    assert "content:attr(data-label)" in compiled_css


def test_dark_theme_overrides_fixed_documentation_surfaces() -> None:
    _html, styles, _app_js, _designer_main = _read_sources()
    _compiled_html, compiled_css, _compiled_js = _read_compiled()
    dark_css = styles[styles.index(':root[data-theme="dark"]') :]
    compact_compiled_css = _compact_css(compiled_css)

    assert "--family-auditory-bg: #3b3424" in dark_css
    assert _rule_has(
        dark_css,
        r':root\[data-theme="dark"\] \.info-lede,[^{]+',
        r"color:\s*var\(--text\)",
    )
    for selector in (
        ".resource-node",
        ".arch-node-resource",
        ".arch-node-runner",
        ".arch-node-hw",
        ".publication-card",
        ".recommended-card",
        ".hardware-pixel-frame",
    ):
        assert _selector_has(dark_css, selector, r"background:\s*var\(--surface-2\)")
    assert _rule_has(
        dark_css,
        r':root\[data-theme="dark"\] \.placeholder-copy,[^{]+',
        r"background:\s*var\(--surface-2\)",
    )
    assert _rule_has(
        dark_css,
        r':root\[data-theme="dark"\] \.arch-hw-dep-link,[^{]+',
        r"color:\s*var\(--primary\)",
    )

    for contract in (
        "--family-auditory-bg:#3b3424",
        ":root[data-theme=dark] .info-lede",
        ":root[data-theme=dark] .resource-node",
        "background:var(--surface-2)",
        "color:var(--text)",
    ):
        assert contract in compact_compiled_css


def test_phone_hides_unavailable_actions_and_keeps_dark_labels_readable() -> None:
    _html, styles, _app_js, _designer_main = _read_sources()
    _compiled_html, compiled_css, _compiled_js = _read_compiled()
    mobile_css = "\n".join(_at_rule_blocks(styles, "@media (max-width: 760px)"))
    compiled_mobile_css = "\n".join(
        _at_rule_blocks(compiled_css, "@media (max-width: 760px)")
    )

    for css in (mobile_css, compiled_mobile_css):
        for selector in (
            ".panel.profile-readonly [data-remove-noise]",
            ".panel.profile-readonly [data-remove-audio]",
        ):
            assert _selector_has(css, selector, r"display:\s*none\s*!important")
        assert _selector_has(
            css,
            "body.desktop-applet .mobile-companion-toggle",
            r"display:\s*none",
        )

    dark_css = styles[styles.index(':root[data-theme="dark"]') :]
    compiled_dark_css = compiled_css[compiled_css.index(":root[data-theme=dark]") :]
    for css, theme_selector in (
        (dark_css, ':root[data-theme="dark"]'),
        (compiled_dark_css, ":root[data-theme=dark]"),
    ):
        for selector in (
            ".arch-hw-label",
            ".audiogram-figcaption .audiogram-figcaption-label",
        ):
            assert _selector_has(
                css,
                f"{theme_selector} {selector}",
                r"color:\s*var\(--muted\)",
            )

    for css in (styles, compiled_css):
        assert _selector_has(css, ".arch-hw-dep-label", r"font-size:\s*11px")
        assert _selector_has(css, ".arch-hw-dep-label", r"letter-spacing:\s*0")
        assert _selector_has(css, ".arch-hw-dep-label", r"color:\s*var\(--primary\)")


def test_modals_contain_focus_and_scroll_within_the_phone_viewport() -> None:
    source_html, styles, app_js, _designer_main = _read_sources()
    compiled_html, compiled_css, compiled_js = _read_compiled()

    for html in (source_html, compiled_html):
        dialogs = _Markup(html).with_role("dialog")
        modal_dialogs = [(tag, attrs) for tag, attrs in dialogs if attrs.get("aria-modal") == "true"]
        nonmodal_dialogs = [(tag, attrs) for tag, attrs in dialogs if attrs.get("aria-modal") == "false"]
        assert len(modal_dialogs) == 3
        assert len(nonmodal_dialogs) == 1
        assert nonmodal_dialogs[0][1]["id"] == "publication-network-detail"
        assert all(attrs["tabindex"] == "-1" for _tag, attrs in dialogs)

    assert _rule_has(styles, r"\.modal-card", r"max-height:\s*calc\(100dvh - 40px\)")
    assert _rule_has(styles, r"\.modal-card", r"overflow-y:\s*auto")
    assert _rule_has(styles, r"\.modal-card", r"overscroll-behavior:\s*contain")
    mobile_css = "\n".join(_at_rule_blocks(styles, "@media (max-width: 760px)"))
    assert _rule_has(mobile_css, r"\.modal-card", r"max-height:\s*calc\(100dvh - 16px\)")
    assert _rule_has(mobile_css, r"\.modal-heading", r"position:\s*sticky")
    assert "@media (min-width: 480px) and (max-width: 760px) and (max-height: 500px) and (orientation: landscape)" in styles

    for contract in (
        "function activeModalBackdrop()",
        "function syncModalEnvironment()",
        "if (shell) shell.inert = open",
        "if (skipLink) skipLink.inert = open",
        "function trapModalFocus(event)",
        'if (event.key !== "Tab") return false',
        "if (event.shiftKey",
        "dialog.contains(document.activeElement)",
        "if (trapModalFocus(event)) return",
    ):
        assert contract in app_js
    assert "max-height:calc(100dvh - 40px);overflow-y:auto;overscroll-behavior:contain" in compiled_css
    for contract in ("modal-open", '[role="dialog"]', "button:not([disabled])", "inert", "Tab"):
        assert contract in compiled_js


def test_collapse_and_noise_choice_states_are_exposed_to_assistive_technology() -> None:
    _html, _styles, app_js, designer_main = _read_sources()
    _compiled_html, _compiled_css, compiled_js = _read_compiled()

    for contract in (
        'button.className = "segment-collapse-button"',
        'button.setAttribute("aria-controls", segment.id)',
        'button.setAttribute("aria-expanded", "true")',
        'button.setAttribute("aria-expanded", String(!collapsed))',
        'button.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} ${kicker}: ${title}`)',
    ):
        assert contract in designer_main
    for contract in (
        'button.setAttribute("aria-pressed", String(active))',
        'button.classList.toggle("active", active)',
        'document.querySelectorAll(".noise-type-button")',
    ):
        assert contract in app_js
    for contract in ("segment-collapse-button", "aria-expanded", "Collapse", "Expand", "noise-type-button", "aria-pressed"):
        assert contract in compiled_js


def test_compiled_dashboard_and_public_wrappers_share_one_cache_token() -> None:
    source_html, _styles, _app_js, _designer_main = _read_sources()
    compiled_html, _compiled_css, _compiled_js = _read_compiled()
    versions = set(
        re.findall(r'(?:styles\.css|app\.js|designer_main\.js)\?v=([a-zA-Z0-9._-]+)', source_html)
    )
    assert len(versions) == 1
    version = versions.pop()
    assert version == "20260807-publication-network"

    wrappers = {
        "toolkit": (ROOT / "index.html").read_text(encoding="utf-8"),
        "documentation": (ROOT / "documentation" / "index.html").read_text(encoding="utf-8"),
        "downloads": (ROOT / "download" / "index.html").read_text(encoding="utf-8"),
    }
    for page, wrapper in wrappers.items():
        route = f"compiled/index.html?page={page}&v={version}"
        assert wrapper.count(route) == 2
        wrapper_versions = set(re.findall(r"compiled/index\.html\?page=[^&\"]+&v=([^\"]+)", wrapper))
        assert wrapper_versions == {version}

    for marker in (
        'class="skip-link"',
        'role="tablist"',
        'id="mobile-rail-nav-toggle"',
        'id="mobile-companion-toggle"',
        'class="data-table mobile-card-table"',
        'role="dialog" aria-modal="true"',
    ):
        assert source_html.count(marker) == compiled_html.count(marker) > 0
