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
NETWORK_ASSET = DASHBOARD / "publication_network.v2.json"
SOURCE_SNAPSHOT = ROOT / "data" / "publication_network" / "citation_snapshot.v1.json"
COVERAGE_AUDIT = ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"


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


def _normalize_doi(value: object) -> str:
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return re.sub(r"[\s.]+$", "", doi)


def _in_scope_coverage_records() -> dict[str, list[dict]]:
    audit = json.loads(COVERAGE_AUDIT.read_text(encoding="utf-8"))
    records_by_doi: dict[str, list[dict]] = {}
    for record in audit["literature_records"]:
        doi = _normalize_doi(record.get("doi"))
        category = record.get("coverage_category")
        if doi and category and category != "adjacent_out_of_scope":
            records_by_doi.setdefault(doi, []).append(record)
    return records_by_doi


def _radial_distance(position: dict[str, float]) -> float:
    return math.hypot(position["x"] - 0.5, position["y"] - 0.5)


def test_publication_network_section_is_semantic_focused_and_uncluttered() -> None:
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

        prominence = markup.by_id("publication-layout-prominence")[1]
        timeline = markup.by_id("publication-layout-year")[1]
        assert prominence["type"] == timeline["type"] == "radio"
        assert prominence["name"] == timeline["name"] == "publication-network-layout"
        assert prominence["value"] == "prominence"
        assert timeline["value"] == "timeline"
        assert "checked" in prominence and "checked" not in timeline

        assert markup.by_id("publication-network-search")[0] == "input"
        assert markup.by_id("publication-network-size-metric")[0] == "select"
        assert markup.by_id("publication-network-edge-mode")[0] == "select"
        assert markup.by_id("publication-network-workspace")[0] == "div"
        assert markup.by_id("publication-network-stage")[0] == "div"
        assert not markup.with_attr("data-network-preset")

        canvas_tag, canvas = markup.by_id("publication-network-canvas")
        assert canvas_tag == "canvas"
        assert canvas["tabindex"] == "0"
        assert "publication-network-help" in (canvas["aria-describedby"] or "").split()
        assert "publication-network-status" in (canvas["aria-describedby"] or "").split()
        assert "square citation map" in (canvas["aria-label"] or "")

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

        for removed_contract in (
            "publication-filter-audiotactile",
            "publication-filter-visuotactile",
            "publication-filter-other",
            "publication-filter-context",
            "publication-filter-provisional",
            "publication-layout-structure",
            "publication-network-map-controls",
            "publication-network-zoom-in",
            "publication-network-zoom-out",
            "publication-network-reset-view",
        ):
            assert f'id="{removed_contract}"' not in html

        assert "Audio–Tactile PPS Experiment and Citation Network" in html
        assert "Reviews and adjacent visual-only or auditory-only studies are excluded" in html
        assert "Runnable Toolkit profile" in html
        assert "Supported paradigm; parameters incomplete" in html


def test_publication_network_source_and_compiled_contracts_stay_in_sync() -> None:
    source_html = _source_html()
    compiled_html = _compiled_html()
    contract_ids = re.findall(r'id="(publication-(?:network|layout)[^"]+)"', source_html)
    assert len(contract_ids) == len(set(contract_ids))
    for element_id in contract_ids:
        assert compiled_html.count(f'id="{element_id}"') == 1

    assert source_html.count('class="doc-segment-rule"') == 9
    assert compiled_html.count('class="doc-segment-rule"') == 9
    for value in (
        "prominence",
        "timeline",
        "withinCorpusReceived",
        "pageRank",
        "betweennessApprox",
        "externalMax",
        "uniform",
        "neighborhood",
        "all",
        "none",
    ):
        assert f'value="{value}"' in source_html
        assert f'value="{value}"' in compiled_html

    edge_mode = re.search(
        r'<option value="neighborhood"([^>]*)>Selected paper only</option>', source_html
    )
    assert edge_mode and "selected" in edge_mode.group(1)


def test_publication_network_module_is_focused_square_and_keyboard_accessible() -> None:
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

    assert "publication_network.v2.json" in network_js
    assert "pps-publication-citation-network.v2" in network_js
    assert list((DASHBOARD / "compiled" / "assets").glob("publication_network.v2-*.json"))

    source_contracts = (
        "publication-network-search",
        "publication-network-layout",
        "publication-network-size-metric",
        "publication-network-edge-mode",
        "publication-network-results",
        "publication-network-detail",
        "publication-network-fullscreen",
        'layout: "prominence"',
        "plotSide",
        "overlapCount",
        "publicationNetworkAudit",
        "publicationNetworkOverlaps",
        "toolkitRecordJoins",
        "requestAnimationFrame",
        "devicePixelRatio",
        "textContent",
        "keydown",
        "ArrowLeft",
        "ArrowRight",
        "Enter",
        "Escape",
    )
    for contract in source_contracts:
        assert contract in network_js

    for compiled_contract in (
        "publication-network-search",
        "publication-network-layout",
        "publication-network-size-metric",
        "publication-network-edge-mode",
        "publication-network-results",
        "publication-network-detail",
        "publication-network-fullscreen",
        "pps-publication-citation-network.v2",
        "prominence",
        "plotSide",
        "overlapCount",
        "publicationNetworkAudit",
        "publicationNetworkOverlaps",
        "toolkitRecordJoins",
        "requestAnimationFrame",
        "devicePixelRatio",
        "textContent",
        "ArrowLeft",
        "ArrowRight",
        "Enter",
        "Escape",
    ):
        assert compiled_contract in compiled_js

    assert "toolkitExperimentRecords" not in network_js
    assert "innerHTML = node." not in network_js
    assert "insertAdjacentHTML" not in network_js
    assert "new Map(state.visible.map" in network_js
    assert "document.fullscreenElement === shell" in network_js
    assert "shell.requestFullscreen()" in network_js
    assert "lastFocusNode" in network_js
    assert 'state.layout = currentLayout()' in network_js
    assert 'root.dataset.publicationNetworkNodes = String(nodes.length)' in network_js
    assert 'root.dataset.publicationNetworkRecords = String(data.counts.toolkitRecordJoins)' in network_js

    for removed_contract in (
        "publication-filter-",
        "data-network-preset",
        "publication-network-map-controls",
        "publication-network-zoom-in",
        "publication-network-zoom-out",
        "publication-network-reset-view",
        "state.zoom",
        "state.pan",
    ):
        assert removed_contract not in network_js


def test_publication_network_styles_cover_square_mobile_theme_and_reduced_motion() -> None:
    styles = (DASHBOARD / "styles.css").read_text(encoding="utf-8")
    compiled_css = _compiled_assets("css")

    for css in (styles, compiled_css):
        compact = _compact_css(css)
        for selector in (
            ".publication-network-shell",
            ".publication-network-shell:fullscreen",
            ".publication-network-toolbar",
            ".publication-network-workspace",
            ".publication-network-workspace.detail-open",
            ".publication-network-stage",
            ".publication-network-detail",
            ".publication-network-results",
            ".publication-network-tooltip",
        ):
            assert selector in css
        for color_variable in (
            "--network-runnable",
            "--network-supported",
            "--network-node-stroke",
            "--network-selection",
            "--network-edge",
            "--network-edge-selected",
        ):
            assert color_variable in css
        assert "aspect-ratio:1 / 1" in compact
        assert "#publication-network-canvas" in css
        assert "width:100%" in compact
        assert "height:100%" in compact
        assert "@media(prefers-reduced-motion:reduce)" in compact
        mobile = compact[compact.index("@media(max-width:760px)") :]
        assert ".publication-network-toolbar" in mobile
        assert ".publication-network-detail" in mobile
        assert "min-height:44px" in mobile

    for removed_variable in ("--network-at", "--network-vt", "--network-provisional"):
        assert removed_variable not in styles


def test_publication_network_asset_is_packaged_and_has_focused_corpus_integrity() -> None:
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    assert dashboard_files.joinpath("publication_network.js").is_file()
    assert dashboard_files.joinpath("publication_network.v2.json").is_file()

    data = _load_network()
    assert data["schema"] == "pps-publication-citation-network.v2"
    assert data["generatorVersion"] == "2.0.0"
    assert data["sourceCounts"] == {
        "nodes": 1712,
        "edges": 10109,
        "audiotactileConfirmed": 101,
        "toolkitRecordJoins": 73,
        "toolkitNodeJoins": 69,
    }
    assert data["counts"] == {
        "nodes": 64,
        "edges": 456,
        "audiotactileConfirmed": 60,
        "toolkitRecordJoins": 68,
        "toolkitNodeJoins": 64,
        "toolkitRunnableNodes": 15,
        "toolkitRunnableRecords": 17,
        "toolkitManualReviewRecords": 24,
        "toolkitManualReviewNodes": 21,
        "abstractsAvailable": 33,
        "abstractsSourceLinkOnly": 28,
        "abstractsNotAvailable": 3,
    }
    nodes = data["nodes"]
    edges = data["edges"]
    assert len(nodes) == 64
    assert len(edges) == 456

    node_ids = [node["id"] for node in nodes]
    assert node_ids == sorted(node_ids)
    assert len(node_ids) == len(set(node_ids))
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
            "toolkit",
            "layouts",
        }
        for node in nodes
    )

    source = json.loads(SOURCE_SNAPSHOT.read_text(encoding="utf-8"))
    assert source["schema"] == "pps-publication-citation-source.v1"
    assert len(source["nodes"]) == 1712
    assert len(source["edges"]) == 10109
    source_by_id = {node["id"]: node for node in source["nodes"]}
    records_by_doi = _in_scope_coverage_records()
    expected_nodes = sorted(
        (
            node
            for node in source["nodes"]
            if node["corpus"]["documentRole"] != "review"
            and _normalize_doi(node["doi"]) in records_by_doi
        ),
        key=lambda node: node["id"],
    )
    assert len(expected_nodes) == 64
    assert node_ids == [node["id"] for node in expected_nodes]

    for node in nodes:
        assert node["corpus"]["documentRole"] != "review"
        records = node["toolkit"]["records"]
        assert records
        assert all(
            record["coverageCategory"]
            and record["coverageCategory"] != "adjacent_out_of_scope"
            for record in records
        )
        audit_record_ids = {
            record["record_id"]
            for record in records_by_doi[_normalize_doi(node["doi"])]
        }
        assert {record["recordId"] for record in records} == audit_record_ids

        source_node = source_by_id[node["id"]]
        assert node["citations"] == source_node["citations"]
        assert node["centrality"] == source_node["centrality"]

    toolkit_records = [record for node in nodes for record in node["toolkit"]["records"]]
    assert len(toolkit_records) == 68
    assert sum(record["recreatable"] for record in toolkit_records) == 17
    assert sum(any(record["recreatable"] for record in node["toolkit"]["records"]) for node in nodes) == 15
    assert sum(record["manualReview"] is not None for record in toolkit_records) == 24
    assert sum(any(record["manualReview"] is not None for record in node["toolkit"]["records"]) for node in nodes) == 21
    assert sum(node["modality"]["audiotactile"]["verified"] for node in nodes) == 60
    assert Counter(node["abstract"]["status"] for node in nodes) == {
        "available": 33,
        "source_link_only": 28,
        "not_available": 3,
    }

    focused_id_set = set(node_ids)
    expected_edges = {
        (
            node_ids.index(edge["source"]),
            node_ids.index(edge["target"]),
            edge["provenance"],
        )
        for edge in source["edges"]
        if edge["source"] in focused_id_set and edge["target"] in focused_id_set
    }
    actual_edges: set[tuple[int, int, str]] = set()
    actual_pairs: set[tuple[int, int]] = set()
    for edge in edges:
        assert isinstance(edge, list) and len(edge) == 3
        source_index, target_index, provenance = edge
        assert isinstance(source_index, int) and 0 <= source_index < len(nodes)
        assert isinstance(target_index, int) and 0 <= target_index < len(nodes)
        assert source_index != target_index
        assert isinstance(provenance, str) and provenance
        assert (source_index, target_index) not in actual_pairs
        actual_pairs.add((source_index, target_index))
        actual_edges.add((source_index, target_index, provenance))
    assert len(expected_edges) == 456
    assert actual_edges == expected_edges

    assert data["methodology"]["edgeDirection"] == "source publication cites target publication"
    assert "not a quality score" in data["methodology"]["centrality"]["influence"]
    assert "normalized DOI only" in data["methodology"]["toolkitJoin"]
    assert "adjacent_out_of_scope" in data["methodology"]["selection"]


def test_publication_network_layouts_are_square_separated_and_semantically_ordered() -> None:
    data = _load_network()
    nodes = data["nodes"]
    bounds = data["layoutBounds"]["grid"]
    assert bounds == {
        "rows": 8,
        "columns": 8,
        "minX": 0.07,
        "maxX": 0.93,
        "minY": 0.07,
        "maxY": 0.93,
        "minimumCenterSpacing": 0.122857,
        "maximumRecommendedNodeRadius": 0.049143,
    }
    assert 2 * bounds["maximumRecommendedNodeRadius"] < bounds["minimumCenterSpacing"]

    for layout_name in ("prominence", "timeline"):
        positions = [node["layouts"][layout_name] for node in nodes]
        assert all(set(position) == {"x", "y"} for position in positions)
        assert all(
            math.isfinite(position[axis])
            and bounds[f"min{axis.upper()}"] <= position[axis] <= bounds[f"max{axis.upper()}"]
            for position in positions
            for axis in ("x", "y")
        )
        slots = {(position["x"], position["y"]) for position in positions}
        assert len(slots) == 64
        assert len({position["x"] for position in positions}) == 8
        assert len({position["y"] for position in positions}) == 8
        for index, left in enumerate(positions):
            for right in positions[index + 1 :]:
                assert math.hypot(left["x"] - right["x"], left["y"] - right["y"]) >= (
                    bounds["minimumCenterSpacing"] - 1e-6
                )

    prominence_order = sorted(
        nodes,
        key=lambda node: (
            -node["citations"]["withinCorpusReceived"],
            -node["centrality"]["pageRank"],
            -node["centrality"]["influence"],
            node["id"],
        ),
    )
    prominence_distances = [
        _radial_distance(node["layouts"]["prominence"])
        for node in prominence_order
    ]
    rounded_prominence_distances = [round(distance, 6) for distance in prominence_distances]
    assert rounded_prominence_distances == sorted(rounded_prominence_distances)
    assert sum(prominence_distances[:16]) / 16 < sum(prominence_distances[-16:]) / 16
    assert data["layoutBounds"]["prominence"]["nodeOrder"] == [
        "withinCorpusReceived desc",
        "pageRank desc",
        "influence desc",
        "id asc",
    ]

    timeline_order = sorted(
        nodes,
        key=lambda node: (
            node["year"] if isinstance(node["year"], int) else math.inf,
            node["title"],
            node["id"],
        ),
    )
    row_major = sorted(
        nodes,
        key=lambda node: (
            node["layouts"]["timeline"]["y"],
            node["layouts"]["timeline"]["x"],
        ),
    )
    assert [node["id"] for node in row_major] == [node["id"] for node in timeline_order]
    timeline_years = [node["year"] for node in row_major if isinstance(node["year"], int)]
    assert timeline_years == sorted(timeline_years)
    assert data["layoutBounds"]["timeline"]["nodeOrder"] == [
        "year asc (unknown last)",
        "title asc",
        "id asc",
    ]

    network_js = (DASHBOARD / "publication_network.js").read_text(encoding="utf-8")
    maximum_radius = float(re.search(r"NODE_RADIUS_MAX\s*=\s*([0-9.]+)", network_js).group(1))
    assert 2 * maximum_radius < bounds["minimumCenterSpacing"]
    assert "Math.min(width, height)" in network_js


def test_publication_network_abstract_policy_is_public_safe() -> None:
    for node in _load_network()["nodes"]:
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
    rebuilt = tmp_path / "publication_network.v2.json"
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
    assert report["schema"] == "pps-publication-citation-network.v2"
    assert report["sourceCounts"] == _load_network()["sourceCounts"]
    assert report["counts"] == _load_network()["counts"]
    assert rebuilt.read_bytes() == NETWORK_ASSET.read_bytes()
