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

        for control_id in (
            "publication-filter-audiotactile",
            "publication-filter-visuotactile",
            "publication-filter-other",
            "publication-filter-context",
            "publication-filter-provisional",
        ):
            tag, attrs = markup.by_id(control_id)
            assert tag == "input"
            assert attrs["type"] == "checkbox"
        assert "checked" in markup.by_id("publication-filter-audiotactile")[1]
        assert "checked" in markup.by_id("publication-filter-provisional")[1]

        structure = markup.by_id("publication-layout-structure")[1]
        timeline = markup.by_id("publication-layout-year")[1]
        assert structure["type"] == timeline["type"] == "radio"
        assert structure["name"] == timeline["name"] == "publication-network-layout"
        assert structure["value"] == "structure"
        assert timeline["value"] == "timeline"
        assert "checked" in structure and "checked" not in timeline

        assert markup.by_id("publication-network-search")[0] == "input"
        assert markup.by_id("publication-network-size-metric")[0] == "select"
        assert markup.by_id("publication-network-edge-mode")[0] == "select"
        assert {
            attrs["data-network-preset"]
            for _tag, attrs in markup.with_attr("data-network-preset")
        } == {"all", "audiotactile", "visuotactile"}

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
        assert markup.by_id("publication-network-results")[0] == "ol"


def test_publication_network_source_and_compiled_contracts_stay_in_sync() -> None:
    source_html = _source_html()
    compiled_html = _compiled_html()
    contract_ids = re.findall(r'id="(publication-(?:network|filter|layout)[^"]+)"', source_html)
    assert len(contract_ids) == len(set(contract_ids))
    for element_id in contract_ids:
        assert compiled_html.count(f'id="{element_id}"') == 1

    assert source_html.count('class="doc-segment-rule"') == 9
    assert compiled_html.count('class="doc-segment-rule"') == 9
    for value in (
        "withinCorpusReceived",
        "pageRank",
        "betweennessApprox",
        "externalMax",
        "uniform",
        "neighborhood",
        "context",
        "all",
        "none",
    ):
        assert f'value="{value}"' in source_html
        assert f'value="{value}"' in compiled_html


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
        "publication-network-size-metric",
        "publication-network-edge-mode",
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
        for color_variable in ("--network-at", "--network-vt", "--network-provisional"):
            assert color_variable in css
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

    assert sum(node["modality"]["audiotactile"]["verified"] for node in nodes) == 101
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
