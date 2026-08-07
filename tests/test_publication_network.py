from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from collections import Counter
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "src" / "peripersonal_space_toolkit" / "dashboard"
NETWORK_ASSET = DASHBOARD / "publication_network.v1.json"


class _Markup(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def by_id(self, element_id: str) -> tuple[str, dict[str, str | None]]:
        return next(element for element in self.elements if element[1].get("id") == element_id)

    def with_attr(self, key: str, value: str | None = None) -> list[tuple[str, dict[str, str | None]]]:
        return [
            element
            for element in self.elements
            if key in element[1] and (value is None or element[1][key] == value)
        ]


def _source_html() -> str:
    return (DASHBOARD / "index.html").read_text(encoding="utf-8")


def _compiled_html() -> str:
    return (DASHBOARD / "compiled" / "index.html").read_text(encoding="utf-8")


def _compiled_assets(suffix: str) -> str:
    paths = sorted((DASHBOARD / "compiled" / "assets").glob(f"*.{suffix}"))
    assert paths, f"compiled dashboard has no .{suffix} assets"
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _compact_css(css: str) -> str:
    return re.sub(r"\s*([:;,{}()])\s*", r"\1", css)


def _select_values(html: str, element_id: str) -> list[str]:
    select = re.search(
        rf'<select\b[^>]*\bid="{re.escape(element_id)}"[^>]*>(.*?)</select>',
        html,
        re.DOTALL,
    )
    assert select, f"missing select #{element_id}"
    return re.findall(r'<option\b[^>]*\bvalue="([^"]+)"', select.group(1))


def _load_network() -> dict:
    return json.loads(NETWORK_ASSET.read_text(encoding="utf-8"))


def test_publication_network_section_is_semantic_in_source_and_compiled() -> None:
    for html in (_source_html(), _compiled_html()):
        markup = _Markup(html)
        section_tag, section = markup.by_id("docs-publication-network")
        assert section_tag == "section"
        assert section["aria-labelledby"] == "docs-publication-network-title"
        assert "data-publication-network-root" in section

        rail_links = markup.with_attr("data-page-section-link", "docs-publication-network")
        assert len(rail_links) == 1
        assert rail_links[0][1]["href"] == "#docs-publication-network"
        assert rail_links[0][1]["data-page-section-page"] == "documentation"

        section_markup = re.search(
            r'<section\b[^>]*\bid="docs-publication-network".*?</section>',
            html,
            re.DOTALL,
        )
        assert section_markup
        title = re.search(
            r'<h2\b[^>]*\bid="docs-publication-network-title"[^>]*>(.*?)</h2>',
            section_markup.group(0),
            re.DOTALL,
        )
        assert title
        title_text = re.sub(r"<[^>]+>", " ", title.group(1)).lower()
        assert "audiotactile" in title_text
        assert "citation map" in title_text
        intro = re.search(
            r'<p\b[^>]*\bclass="[^"]*publication-network-intro[^"]*"[^>]*>(.*?)</p>',
            section_markup.group(0),
            re.DOTALL,
        )
        assert intro
        intro_text = re.sub(r"<[^>]+>", " ", intro.group(1)).lower()
        assert "audiotactile" in intro_text
        assert "manually verified" in intro_text

        structure = markup.by_id("publication-layout-structure")[1]
        timeline = markup.by_id("publication-layout-year")[1]
        assert structure["type"] == timeline["type"] == "radio"
        assert structure["name"] == timeline["name"] == "publication-network-layout"
        assert structure["value"] == "structure"
        assert timeline["value"] == "timeline"
        assert "checked" in structure and "checked" not in timeline

        assert markup.by_id("publication-network-search")[0] == "input"
        assert markup.by_id("publication-network-reset")[0] == "button"

        canvas_tag, canvas = markup.by_id("publication-network-canvas")
        assert canvas_tag == "canvas"
        assert canvas["tabindex"] == "0"
        assert "publication-network-help" in (canvas["aria-describedby"] or "").split()
        assert "publication-network-status" in (canvas["aria-describedby"] or "").split()

        status = markup.by_id("publication-network-status")[1]
        assert status["role"] == "status"
        assert status["aria-live"] == "polite"
        detail = markup.by_id("publication-network-detail")[1]
        assert detail["role"] == "dialog"
        assert detail["aria-modal"] == "false"
        assert detail["aria-labelledby"] == "publication-network-detail-title"
        assert detail["tabindex"] == "-1"
        assert "hidden" in detail
        assert markup.by_id("publication-network-detail-close")[0] == "button"

        study_lists = markup.with_attr("aria-label", "Audiotactile study list")
        assert len(study_lists) == 1
        assert study_lists[0][0] == "aside"
        assert re.search(
            r'<aside\b[^>]*\baria-label="Audiotactile study list"[^>]*>'
            r'.*?<h[2-4]\b[^>]*>[^<]*studies[^<]*</h[2-4]>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        assert _select_values(html, "publication-network-results-sort") == [
            "audiotactileReceived",
            "year-desc",
            "year-asc",
            "title",
        ]
        assert markup.by_id("publication-network-results")[0] == "ol"
        assert markup.by_id("publication-network-results-more")[0] == "button"

        for removed_id in (
            "publication-filter-audiotactile",
            "publication-filter-visuotactile",
            "publication-filter-other",
            "publication-filter-context",
            "publication-filter-provisional",
            "publication-network-size-metric",
            "publication-network-edge-mode",
        ):
            assert f'id="{removed_id}"' not in html
        assert "data-network-preset" not in html


def test_publication_network_source_and_compiled_contracts_stay_in_sync() -> None:
    source_html = _source_html()
    compiled_html = _compiled_html()
    contract_ids = re.findall(r'id="(publication-(?:network|filter|layout)[^"]+)"', source_html)
    assert len(contract_ids) == len(set(contract_ids))
    for element_id in contract_ids:
        assert compiled_html.count(f'id="{element_id}"') == 1

    assert source_html.count('class="doc-segment-rule"') == 9
    assert compiled_html.count('class="doc-segment-rule"') == 9
    for value in ("audiotactileReceived", "year-desc", "year-asc", "title"):
        assert f'value="{value}"' in source_html
        assert f'value="{value}"' in compiled_html

    for removed_contract in (
        "publication-filter-audiotactile",
        "publication-filter-visuotactile",
        "publication-filter-other",
        "publication-filter-context",
        "publication-filter-provisional",
        "publication-network-size-metric",
        "publication-network-edge-mode",
        "data-network-preset",
    ):
        assert removed_contract not in source_html
        assert removed_contract not in compiled_html


def test_publication_network_module_is_lazy_interactive_and_keyboard_accessible() -> None:
    app_js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    network_js = (DASHBOARD / "publication_network.js").read_text(encoding="utf-8")
    compiled_js = _compiled_assets("js")

    for contract in (
        "data-publication-network-root",
        "IntersectionObserver",
        "publication_network.js",
        "initializePublicationNetwork",
    ):
        assert contract in app_js
    for contract in ("data-publication-network-root", "IntersectionObserver", "publication_network"):
        assert contract in compiled_js

    assert "publication_network.v1.json" in network_js
    assert list((DASHBOARD / "compiled" / "assets").glob("publication_network.v1-*.json"))

    for contract in (
        "publication-network-search",
        "publication-network-layout",
        "publication-network-reset",
        "publication-network-results",
        "publication-network-detail",
        "publication-network-fullscreen",
        "requestAnimationFrame",
        "devicePixelRatio",
        "textContent",
        "keydown",
        "ArrowLeft",
        "ArrowRight",
        "Enter",
        "Escape",
    ):
        assert contract in network_js
        assert contract in compiled_js

    for source_contract in (
        "verifiedAudiotactile",
        "audiotactileEdges",
        "audiotactileReceived",
    ):
        assert source_contract in network_js
    assert "modality?.audiotactile?.verified" in network_js
    assert re.search(r"state\.visible\s*=\s*verifiedAudiotactile\.filter", network_js)
    assert re.search(r"landmark", network_js, re.IGNORECASE)
    assert "geometry.width < 520 ? 0" in network_js

    fit_start = network_js.index("function fitView()")
    fit_end = network_js.index("\n  function zoom(", fit_start)
    fit_source = network_js[fit_start:fit_end]
    assert "state.visible" in fit_source
    assert "positionFor" in fit_source
    assert "state.view.scale" in fit_source
    assert "state.view.x" in fit_source
    assert "state.view.y" in fit_source
    assert "state.view = { scale: 1, x: 0, y: 0 };" not in fit_source

    for removed_contract in (
        "publication-filter-audiotactile",
        "publication-filter-visuotactile",
        "publication-filter-other",
        "publication-filter-context",
        "publication-filter-provisional",
        "publication-network-size-metric",
        "publication-network-edge-mode",
        "data-network-preset",
    ):
        assert removed_contract not in network_js
        assert removed_contract not in compiled_js

    assert "innerHTML = node." not in network_js
    assert "insertAdjacentHTML" not in network_js
    assert "new Map(state.visible.map" in network_js
    assert "document.fullscreenElement === shell" in network_js
    assert "shell.requestFullscreen()" in network_js
    assert "lastFocusNode" in network_js


def test_publication_network_styles_cover_mobile_theme_and_reduced_motion() -> None:
    styles = (DASHBOARD / "styles.css").read_text(encoding="utf-8")
    compiled_css = _compiled_assets("css")

    for css in (styles, compiled_css):
        compact = _compact_css(css)
        for selector in (
            ".publication-network-shell",
            ".publication-network-shell:fullscreen",
            ".publication-network-toolbar",
            ".publication-network-stage",
            ".publication-network-detail",
            ".publication-network-results",
            ".publication-network-tooltip",
        ):
            assert selector in css
        assert "--network-at" in css
        assert "@media(prefers-reduced-motion:reduce)" in compact
        mobile = compact[compact.index("@media(max-width:760px)") :]
        assert ".publication-network-toolbar" in mobile
        assert ".publication-network-detail" in mobile


def test_publication_network_asset_is_packaged_and_has_fixed_corpus_integrity() -> None:
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    assert dashboard_files.joinpath("publication_network.js").is_file()
    assert dashboard_files.joinpath("publication_network.v1.json").is_file()

    data = _load_network()
    assert data["schema"] == "pps-publication-citation-network.v1"
    assert data["counts"] == {
        "nodes": 1712,
        "edges": 10109,
        "audiotactileConfirmed": 101,
        "visuotactileVerified": 0,
        "visuotactileProvisional": 164,
        "toolkitRecordJoins": 73,
        "toolkitNodeJoins": 69,
        "toolkitManualReviewRecords": 24,
        "toolkitManualReviewNodes": 21,
        "abstractsAvailable": 42,
        "abstractsSourceLinkOnly": 1082,
        "abstractsNotAvailable": 588,
        "isolatedNodes": 718,
    }
    nodes = data["nodes"]
    edges = data["edges"]
    assert len(nodes) == 1712
    assert len(edges) == 10109

    node_ids = [node["id"] for node in nodes]
    assert len(node_ids) == len(set(node_ids))
    source = json.loads(
        (ROOT / "data" / "publication_network" / "citation_snapshot.v1.json").read_text(encoding="utf-8")
    )
    assert node_ids == [node["id"] for node in source["nodes"]]
    assert all(
        set(node) == {
            "id",
            "title",
            "year",
            "publicationDate",
            "doi",
            "pmid",
            "openAlexIds",
            "semanticScholarIds",
            "authors",
            "venue",
            "abstract",
            "keywords",
            "topics",
            "corpus",
            "modality",
            "citations",
            "centrality",
            "links",
            "metadata",
            "layouts",
            "toolkit",
        }
        for node in nodes
    )

    edge_pairs: list[tuple[int, int]] = []
    incoming = [0] * len(nodes)
    outgoing = [0] * len(nodes)
    for edge in edges:
        assert isinstance(edge, list) and len(edge) == 3
        source_index, target_index, provenance = edge
        assert isinstance(source_index, int) and 0 <= source_index < len(nodes)
        assert isinstance(target_index, int) and 0 <= target_index < len(nodes)
        assert source_index != target_index
        assert isinstance(provenance, str) and provenance
        edge_pairs.append((source_index, target_index))
        outgoing[source_index] += 1
        incoming[target_index] += 1
    assert len(edge_pairs) == len(set(edge_pairs))
    assert incoming == [node["citations"]["withinCorpusReceived"] for node in nodes]
    assert outgoing == [node["citations"]["withinCorpusReferences"] for node in nodes]
    assert data["methodology"]["edgeDirection"] == "source publication cites target publication"
    assert "not a quality score" in data["methodology"]["centrality"]["influence"]
    assert "normalized DOI only" in data["methodology"]["toolkitJoin"]


def test_publication_network_evidence_metrics_coordinates_and_abstract_policy() -> None:
    data = _load_network()
    nodes = data["nodes"]

    verified_audiotactile = {
        index
        for index, node in enumerate(nodes)
        if node["modality"]["audiotactile"]["verified"]
    }
    assert len(verified_audiotactile) == data["counts"]["audiotactileConfirmed"] == 101
    audiotactile_edges = [
        edge
        for edge in data["edges"]
        if edge[0] in verified_audiotactile and edge[1] in verified_audiotactile
    ]
    assert len(audiotactile_edges) == 635
    assert data["layoutBounds"]["audiotactileStructure"] == {
        "connectedNodeCount": 78,
        "isolatedNodeCount": 23,
    }
    assert data["layoutBounds"]["audiotactileTimeline"]["minYear"] == 2000
    assert data["layoutBounds"]["audiotactileTimeline"]["maxYear"] == 2026
    assert "verified audiotactile induced citation subgraph" in data["methodology"]["layouts"]["audiotactileStructure"]
    assert sum(node["modality"]["visuotactile"]["verified"] for node in nodes) == 0
    assert sum(
        node["modality"]["visuotactile"]["status"] == "provisional_keyword_candidate"
        for node in nodes
    ) == 164

    toolkit_nodes = [node for node in nodes if node["toolkit"]["records"]]
    toolkit_records = [record for node in toolkit_nodes for record in node["toolkit"]["records"]]
    assert len(toolkit_nodes) == 69
    assert len(toolkit_records) == 73
    assert sum(record["manualReview"] is not None for record in toolkit_records) == 24
    assert sum(any(record["manualReview"] is not None for record in node["toolkit"]["records"]) for node in nodes) == 21
    assert Counter(node["abstract"]["status"] for node in nodes) == {
        "available": 42,
        "source_link_only": 1082,
        "not_available": 588,
    }
    for node in nodes:
        for layout_name in ("structure", "timeline"):
            coordinates = node["layouts"][layout_name]
            assert set(coordinates) == {"x", "y"}
            assert all(
                math.isfinite(coordinates[axis]) and 0.0 <= coordinates[axis] <= 1.0
                for axis in ("x", "y")
            )
        if node["modality"]["audiotactile"]["verified"]:
            for layout_name in ("audiotactileStructure", "audiotactileTimeline"):
                coordinates = node["layouts"][layout_name]
                assert set(coordinates) == {"x", "y"}
                assert all(
                    math.isfinite(coordinates[axis]) and 0.0 <= coordinates[axis] <= 1.0
                    for axis in ("x", "y")
                )
        else:
            assert "audiotactileStructure" not in node["layouts"]
            assert "audiotactileTimeline" not in node["layouts"]
        for metric in ("withinCorpusReceived", "withinCorpusReferences", "externalMax"):
            value = node["citations"][metric]
            assert isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
        for metric in ("pageRank", "betweennessApprox", "influence"):
            value = node["centrality"][metric]
            assert isinstance(value, (int, float)) and math.isfinite(value) and value >= 0

        abstract = node["abstract"]
        assert abstract["status"] in {"available", "source_link_only", "not_available"}
        if abstract["status"] == "available":
            assert abstract["text"].strip()
            assert abstract["source"] == "OpenAlex"
            assert abstract["license"] == "CC0-1.0"
            assert abstract["sourceUrl"].startswith("https://openalex.org/")
        else:
            assert abstract["text"] is None
            assert abstract["license"] is None
            assert abstract["caveat"].strip()


def test_publication_network_generator_rebuild_is_byte_deterministic(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        return
    rebuilt = tmp_path / "publication_network.v1.json"
    completed = subprocess.run(
        [node, str(ROOT / "tools" / "build_publication_network_asset.mjs"), "--output", str(rebuilt)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["schema"] == "pps-publication-citation-network.v1"
    assert report["counts"] == _load_network()["counts"]
    assert rebuilt.read_bytes() == NETWORK_ASSET.read_bytes()
