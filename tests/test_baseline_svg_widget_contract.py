from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "src" / "peripersonal_space_toolkit" / "dashboard"
BASELINE_GRAPHICS = {
    "none": "baseline_none.svg",
    "min_anchor": "baseline_min_anchor.svg",
    "max_anchor": "baseline_max_anchor.svg",
    "min_max": "baseline_min_max.svg",
    "tactile_only": "baseline_tactile_only.svg",
    "stationary_burst": "baseline_stationary_burst.svg",
    "custom": "baseline_custom.svg",
}


class _BaselineCardParser(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.cards: dict[str, list[tuple[str, dict[str, str | None]]]] = {}
        self._active_card: str | None = None
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "label" and attributes.get("data-baseline-option"):
            self._active_card = attributes["data-baseline-option"]
            assert self._active_card is not None
            self.cards[self._active_card] = []
            return
        if self._active_card is not None:
            self.cards[self._active_card].append((tag, attributes))

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self._active_card = None


def _css_rule(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^{{}}]*)\}}", css, flags=re.S)
    assert match, f"missing CSS rule: {selector}"
    return match.group("body")


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


def test_baseline_strategy_radios_have_matching_decorative_svg_previews() -> None:
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    parser = _BaselineCardParser(html)

    assert list(parser.cards) == list(BASELINE_GRAPHICS)
    for value, filename in BASELINE_GRAPHICS.items():
        children = parser.cards[value]
        radios = [attrs for tag, attrs in children if tag == "input" and attrs.get("type") == "radio"]
        previews = [
            attrs
            for tag, attrs in children
            if tag == "img"
            and "baseline-option-graphic" in (attrs.get("class") or "").split()
        ]

        assert len(radios) == 1
        assert radios[0]["name"] == "baseline-option"
        assert radios[0]["value"] == value
        assert "disabled" not in radios[0]

        assert len(previews) == 1
        assert previews[0] == {
            "class": "baseline-option-graphic native-signal-graphic",
            "src": filename,
            "alt": "",
            "aria-hidden": "true",
            "width": "320",
            "height": "96",
        }


def test_baseline_strategy_previews_use_compact_responsive_card_layout() -> None:
    css = (DASHBOARD / "styles.css").read_text(encoding="utf-8")
    card = _css_rule(css, ".baseline-option-card")
    graphic = _css_rule(css, ".baseline-option-graphic")

    assert "grid-template-areas:" in card
    assert '"graphic graphic"' in card
    assert card.index('"radio title"') < card.index('"graphic graphic"')
    assert "min-width: 0" in card
    assert "aspect-ratio: 10 / 3" in graphic
    assert "max-width" not in graphic
    assert "background: transparent" in graphic
    assert "border: 0" in graphic
    assert "object-fit: contain" in graphic

    radio = _css_rule(css, ".baseline-option-card input")
    assert "min-height: 0" in radio
    assert "height: 18px" in radio
    assert "appearance: none" in radio
    assert ":root .baseline-option-card.active input" in css

    native_graphic = _css_rule(css, ".native-signal-graphic")
    assert "color-scheme: inherit" in native_graphic

    forced_colors = "\n".join(_at_rule_blocks(css, "@media (forced-colors: active)"))
    assert ".baseline-option-card input" in forced_colors
    assert "appearance: auto" in forced_colors
    assert "forced-color-adjust: auto" in forced_colors

    mobile = "\n".join(_at_rule_blocks(css, "@media (max-width: 760px)"))
    assert mobile
    assert any(
        ".baseline-tactile-panel .baseline-option-grid" in selectors
        and re.search(r"grid-template-columns:\s*1fr", declarations)
        for selectors, declarations in re.findall(
            r"([^{}]+)\{([^{}]*)\}", mobile, flags=re.S
        )
    )
