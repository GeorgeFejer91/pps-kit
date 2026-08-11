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
NETWORK_ASSET = DASHBOARD / "publication_network.v3.json"
SOURCE_SNAPSHOT = ROOT / "data" / "publication_network" / "citation_snapshot.v1.json"
CITATION_OVERLAY = (
    ROOT
    / "data"
    / "publication_network"
    / "openalex_audiotactile_citation_overlay.20260808.json"
)
PRIMARY_SOURCE_CITATION_OVERLAY = (
    ROOT
    / "data"
    / "publication_network"
    / "primary_source_citation_overlay.20260808.json"
)
COVERAGE_AUDIT = ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
PRELOAD_INVENTORY = ROOT / "assets" / "preloads" / "preload_inventory.json"


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


def _load_source() -> dict:
    return json.loads(SOURCE_SNAPSHOT.read_text(encoding="utf-8"))


def _load_citation_overlay() -> dict:
    return json.loads(CITATION_OVERLAY.read_text(encoding="utf-8"))


def _load_primary_source_citation_overlay() -> dict:
    return json.loads(PRIMARY_SOURCE_CITATION_OVERLAY.read_text(encoding="utf-8"))


def _normalize_doi(value: object) -> str:
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return re.sub(r"[\s.]+$", "", doi)


def _has_verified_doi_url(node: dict) -> bool:
    doi = _normalize_doi(node.get("doi"))
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", doi, flags=re.IGNORECASE)) and (
        node.get("id") == f"doi:{doi}"
        and node.get("links", {}).get("doi") == f"https://doi.org/{doi}"
    )


def _citation_metadata_providers(node: dict) -> list[str]:
    sources = set(node.get("metadata", {}).get("sources", []))
    citations = node.get("citations", {}).get("providers", {})
    available: list[str] = []
    if (
        "openalex" in sources
        and node.get("openAlexIds")
        and isinstance(citations.get("openAlex"), (int, float))
        and citations["openAlex"] >= 0
    ):
        available.append("OpenAlex")
    if (
        "semantic_scholar" in sources
        and node.get("semanticScholarIds")
        and isinstance(citations.get("semanticScholar"), (int, float))
        and citations["semanticScholar"] >= 0
    ):
        available.append("Semantic Scholar")
    if (
        "europe_pmc" in sources
        and node.get("pmid")
        and isinstance(citations.get("europePmc"), (int, float))
        and citations["europePmc"] >= 0
    ):
        available.append("Europe PMC")
    return available


def _has_citation_metadata(node: dict) -> bool:
    return bool(_citation_metadata_providers(node))


def _coverage_records_by_doi() -> dict[str, list[dict]]:
    audit = json.loads(COVERAGE_AUDIT.read_text(encoding="utf-8"))
    records_by_doi: dict[str, list[dict]] = {}
    for record in audit["literature_records"]:
        doi = _normalize_doi(record.get("doi"))
        if doi:
            records_by_doi.setdefault(doi, []).append(record)
    return records_by_doi


def _record_is_in_scope(record: dict) -> bool:
    category = record.get("coverage_category") or record.get("coverageCategory")
    return bool(category) and category != "adjacent_out_of_scope"


def _expected_toolkit_status(records: list[dict]) -> str:
    in_scope = [record for record in records if _record_is_in_scope(record)]
    if any(
        record.get("can_recreate_audiotactile_components_now", record.get("recreatable", False))
        for record in in_scope
    ):
        return "runnable"
    if in_scope:
        return "supported_incomplete"
    return "adjacent_scope_conflict" if records else "not_assessed"


def _mean(values: list[float]) -> float:
    assert values
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        rank = (start + end - 1) / 2
        for index in range(start, end):
            ranks[ordered[index][0]] = rank
        start = end
    return ranks


def _spearman(left: list[float], right: list[float]) -> float:
    assert len(left) == len(right) and left
    left_ranks = _ranks(left)
    right_ranks = _ranks(right)
    left_mean = _mean(left_ranks)
    right_mean = _mean(right_ranks)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_ranks, right_ranks, strict=True)
    )
    left_square = sum((value - left_mean) ** 2 for value in left_ranks)
    right_square = sum((value - right_mean) ** 2 for value in right_ranks)
    return numerator / math.sqrt(left_square * right_square)


def _weak_adjacency(node_count: int, edges: list[list]) -> list[set[int]]:
    adjacency = [set() for _ in range(node_count)]
    for source, target, _provenance in edges:
        adjacency[source].add(target)
        adjacency[target].add(source)
    return adjacency


def _weak_components(adjacency: list[set[int]]) -> list[set[int]]:
    unseen = set(range(len(adjacency)))
    components: list[set[int]] = []
    while unseen:
        start = min(unseen)
        component = {start}
        frontier = [start]
        unseen.remove(start)
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency[current]:
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    component.add(neighbour)
                    frontier.append(neighbour)
        components.append(component)
    return sorted(components, key=lambda component: (-len(component), min(component)))


def test_publication_network_section_is_semantic_and_defaults_to_the_network() -> None:
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

        topology = markup.by_id("publication-layout-topology")[1]
        timeline = markup.by_id("publication-layout-year")[1]
        assert topology["type"] == timeline["type"] == "radio"
        assert topology["name"] == timeline["name"] == "publication-network-layout"
        assert topology["value"] == "topology"
        assert timeline["value"] == "timeline"
        assert "checked" in topology and "checked" not in timeline

        assert markup.by_id("publication-network-results-sort")[0] == "select"
        assert markup.by_id("publication-network-workspace")[0] == "div"
        assert markup.by_id("publication-network-stage")[0] == "div"

        graph_tag, graph = markup.by_id("publication-network-graph")
        assert graph_tag == "svg"
        assert graph["role"] == "img"
        assert graph["tabindex"] == "0"
        assert graph["focusable"] == "true"
        assert graph["preserveaspectratio"] == "none"
        assert "publication-network-help" in (graph["aria-describedby"] or "").split()
        assert "publication-network-status" in (graph["aria-describedby"] or "").split()
        assert "publication-network-size-note" in (graph["aria-describedby"] or "").split()
        assert "citation network" in (graph["aria-label"] or "")
        assert "Use the publication list" in (graph["aria-label"] or "")

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

        workspace_position = html.index('id="publication-network-workspace"')
        utilities_position = html.index('class="publication-network-utilities"')
        help_position = html.index('id="publication-network-help"')
        assert workspace_position < utilities_position < help_position

        for removed_contract in (
            "publication-layout-prominence",
            "publication-network-size-metric",
            "publication-filter-audiotactile",
            "publication-filter-visuotactile",
            "publication-filter-other",
            "publication-network-map-controls",
            "publication-network-zoom-in",
            "publication-network-zoom-out",
            "publication-network-reset-view",
            "publication-network-edge-mode",
            "publication-network-search",
        ):
            assert f'id="{removed_contract}"' not in html
        assert 'value="prominence"' not in html

        assert "Audio–Tactile PPS Study Citation Network" in html
        assert "a curated cross-section of audio–tactile peripersonal-space research" in html
        assert "main experimental paradigms and design variations" in html
        assert "not a systematic or exhaustive review" in html
        assert "Each of the 94 non-review publications" not in html
        assert "Implemented in Toolkit" in html
        assert "Not implemented yet" in html
        assert "Circle area increases with incoming citations from other papers" in html
        assert "Larger circle = cited by more included papers" in html
        assert "without an artificial perimeter" in html


def test_publication_network_source_and_compiled_contracts_stay_in_sync() -> None:
    source_html = _source_html()
    compiled_html = _compiled_html()
    contract_ids = re.findall(r'id="(publication-(?:network|layout)[^"]+)"', source_html)
    assert len(contract_ids) == len(set(contract_ids))
    for element_id in contract_ids:
        assert compiled_html.count(f'id="{element_id}"') == 1

    for value in (
        "topology",
        "timeline",
        "networkReceived",
        "review-priority",
        "networkPageRank",
        "year-desc",
        "year-asc",
        "title",
    ):
        assert f'value="{value}"' in source_html
        assert f'value="{value}"' in compiled_html

    source_compiled_assets = DASHBOARD / "compiled" / "assets"
    assert list(source_compiled_assets.glob("publication_network.v3-*.json"))
    assert not list(source_compiled_assets.glob("publication_network.v2-*.json"))


def test_publication_network_module_is_topological_and_keyboard_accessible() -> None:
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

    source_contracts = (
        "publication_network.v3.json",
        "pps-publication-citation-network.v3",
        "publication-network-layout",
        "publication-network-results-sort",
        "publication-network-results",
        "publication-network-detail",
        "publication-network-fullscreen",
        "publication-network-graph",
        "SVG_NAMESPACE",
        "createElementNS",
        'renderer: "inline-svg"',
        'publicationNetworkRenderer = "inline-svg"',
        "publication-network-edge-line",
        "publication-network-node-mark",
        "designerTemplateUrl",
        "designerTemplateLink",
        'url.searchParams.set("page", "toolkit")',
        'url.searchParams.set("template", templateId)',
        'url.hash = "study-segment"',
        'target: "_blank"',
        'rel: "noopener noreferrer"',
        '"data-open-designer-template": templateId',
        "records.flatMap",
        "Open in Experiment Designer",
        'layout: "topology"',
        "nodes[index].network?.radius",
        "network?.inDegree",
        "network?.pageRank",
        "plotWidth",
        "plotHeight",
        "drawnEdgeCount",
        "overlapCount",
        "publicationNetworkAudit",
        "publicationNetworkOverlaps",
        "toolkitRecordJoins",
        "requestAnimationFrame",
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
        "publication_network.v3",
        "pps-publication-citation-network.v3",
        "publication-network-layout",
        "publication-network-results-sort",
        "publication-network-results",
        "publication-network-detail",
        "publication-network-fullscreen",
        "publication-network-graph",
        "inline-svg",
        "createElementNS",
        "publication-network-edge-line",
        "publication-network-node-mark",
        "data-open-designer-template",
        "Open in Experiment Designer",
        "study-segment",
        "template",
        "topology",
        "plotWidth",
        "plotHeight",
        "drawnEdgeCount",
        "overlapCount",
        "publicationNetworkAudit",
        "publicationNetworkOverlaps",
        "toolkitRecordJoins",
        "requestAnimationFrame",
        "textContent",
        "ArrowLeft",
        "ArrowRight",
        "Enter",
        "Escape",
    ):
        assert compiled_contract in compiled_js

    assert "innerHTML = node." not in network_js
    assert "insertAdjacentHTML" not in network_js
    assert "getContext" not in network_js
    assert "devicePixelRatio" not in network_js
    assert "new Map(state.visible.map" in network_js
    assert "document.fullscreenElement === shell" in network_js
    assert "shell.requestFullscreen()" in network_js
    assert "lastFocusNode" in network_js
    assert 'state.layout = currentLayout()' in network_js
    assert 'root.dataset.publicationNetworkNodes = String(nodes.length)' in network_js
    assert 'root.dataset.publicationNetworkEdges = String(edges.length)' in network_js
    assert 'root.dataset.publicationNetworkRecords = String(data.counts.toolkitRecordJoins)' in network_js
    assert "DOI unavailable" not in network_js
    assert "DOI unavailable" not in compiled_js
    assert "displayedPublicationCount = nodes.length.toLocaleString()" in network_js
    for contract in (
        'const TEMPLATE_QUERY_PARAM = "template"',
        "INITIAL_TEMPLATE_REQUEST",
        "pendingInitialTemplateRequest",
        "initialTemplateRequestHandled",
        "The requested Toolkit template is not available in this Designer.",
        "Opened the paper's Toolkit template in Experiment Designer.",
        'link.hasAttribute("data-open-designer-template")',
    ):
        assert contract in app_js
    for compiled_contract in (
        "data-open-designer-template",
        "The requested Toolkit template is not available in this Designer.",
        "Opened the paper's Toolkit template in Experiment Designer.",
    ):
        assert compiled_contract in compiled_js
    assert "97 displayed publications" not in network_js
    assert "97 displayed publications" not in compiled_js

    for removed_contract in (
        "publication_network.v2",
        "pps-publication-citation-network.v2",
        "publication-network-size-metric",
        "controls.sizeMetric",
        "state.metricMaximum",
        'layout: "prominence"',
        ".layouts.prominence",
        "publication-filter-",
        "data-network-preset",
        "publication-network-map-controls",
        "publication-network-zoom-in",
        "publication-network-zoom-out",
        "publication-network-reset-view",
        "state.zoom",
        "state.pan",
        "publication-network-edge-mode",
        "controls.edgeMode",
        "shouldDrawEdge",
        "nodeSearchText",
        "searchActive",
        "searchMatchCount",
        "matchSet",
        "controls.search",
    ):
        assert removed_contract not in network_js


def test_publication_network_styles_cover_simple_statuses_mobile_and_theme() -> None:
    styles = (DASHBOARD / "styles.css").read_text(encoding="utf-8")
    compiled_css = _compiled_assets("css")

    for css in (styles, compiled_css):
        compact = _compact_css(css)
        for selector in (
            ".publication-network-shell",
            ".publication-network-shell:fullscreen",
            ".publication-network-utilities",
            ".publication-network-layout-group",
            ".publication-network-segmented",
            ".publication-network-workspace",
            ".publication-network-workspace.detail-open",
            ".publication-network-stage",
            ".publication-network-detail",
            ".publication-network-results",
            ".publication-network-tooltip",
            ".legend-node-implemented",
            ".legend-node-not-implemented",
            ".legend-line-incoming",
            ".legend-line-outgoing",
            ".publication-network-edge-line",
            ".publication-network-edge.incoming .publication-network-edge-line",
            ".publication-network-edge.outgoing .publication-network-edge-line",
            ".publication-network-node",
            ".publication-network-node-mark.implemented .publication-network-node",
            ".publication-network-node-mark.selected .publication-network-node-selection",
            ".publication-network-template-links a",
        ):
            assert selector in css
        for color_variable in (
            "--network-runnable",
            "--network-supported",
            "--network-unassessed",
            "--network-conflict",
            "--network-conflict-stroke",
            "--network-node-stroke",
            "--network-selection",
            "--network-edge",
            "--network-edge-incoming",
            "--network-edge-outgoing",
        ):
            assert color_variable in css
        assert "aspect-ratio:1 / 1" in compact
        assert "#publication-network-graph" in css
        assert "fill:var(--network-unassessed)" in compact
        assert "fill:var(--network-runnable)" in compact
        assert "stroke:var(--network-edge)" in compact
        assert "stroke:var(--network-edge-incoming)" in compact
        assert "stroke:var(--network-edge-outgoing)" in compact
        assert "width:100%" in compact
        assert "height:100%" in compact
        assert "@media(prefers-reduced-motion:reduce)" in compact
        mobile = compact[compact.index("@media(max-width:760px)") :]
        assert ".publication-network-utilities" in mobile
        assert ".publication-network-detail" in mobile
        assert "min-height:44px" in mobile
        assert "aspect-ratio:1 / 1" in mobile
        assert "grid-template-columns:repeat(2,minmax(0,1fr))" in compact

    for removed_variable in (
        "--network-at",
        "--network-vt",
        "--network-provisional",
        "--network-edge-selected",
    ):
        assert removed_variable not in styles


def test_publication_network_template_links_resolve_to_bundled_profiles() -> None:
    data = _load_network()
    inventory = json.loads(PRELOAD_INVENTORY.read_text(encoding="utf-8"))
    available_template_ids = {profile["template_id"] for profile in inventory["profiles"]}
    node_template_ids = [
        sorted({template_id for record in node["toolkit"]["records"] for template_id in record.get("templateIds", [])})
        for node in data["nodes"]
    ]
    linked_template_ids = {template_id for template_ids in node_template_ids for template_id in template_ids}

    assert linked_template_ids
    assert linked_template_ids <= available_template_ids
    assert any(len(template_ids) == 0 for template_ids in node_template_ids)
    assert any(len(template_ids) == 1 for template_ids in node_template_ids)
    assert any(len(template_ids) > 1 for template_ids in node_template_ids)


def test_publication_network_asset_has_the_exact_decision_landscape_scope() -> None:
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    assert dashboard_files.joinpath("publication_network.js").is_file()
    assert dashboard_files.joinpath("publication_network.v3.json").is_file()
    assert not dashboard_files.joinpath("publication_network.v2.json").is_file()

    data = _load_network()
    assert data["schema"] == "pps-publication-citation-network.v3"
    assert data["generatorVersion"] == "3.4.0"
    assert data["sourceCounts"] == {
        "nodes": 1712,
        "edges": 10109,
        "audiotactileConfirmed": 101,
        "toolkitRecordJoins": 73,
        "toolkitNodeJoins": 69,
    }
    assert data["counts"] == {
        "nodes": 94,
        "edges": 750,
        "audiotactileConfirmed": 90,
        "laterAuditAdditions": 4,
        "toolkitRecordJoins": 69,
        "toolkitInScopeRecordJoins": 68,
        "toolkitNodeJoins": 65,
        "toolkitInScopeNodeJoins": 64,
        "toolkitRunnableNodes": 15,
        "toolkitRunnableRecords": 17,
        "toolkitSupportedIncompleteNodes": 49,
        "toolkitNotAssessedNodes": 29,
        "toolkitAdjacentConflictNodes": 1,
        "toolkitManualReviewRecords": 24,
        "toolkitManualReviewNodes": 21,
        "connectedNodes": 91,
        "isolatedNodes": 3,
        "weakComponents": 4,
        "abstractsAvailable": 37,
        "abstractsSourceLinkOnly": 48,
        "abstractsNotAvailable": 9,
    }
    assert data["selectionAudit"] == {
        "candidatePublications": 97,
        "withVerifiedDoiUrl": 94,
        "doiResolverVerified": 94,
        "withCitationMetadata": 94,
        "excludedMissingVerifiedDoiUrl": 3,
        "excludedMissingCitationMetadata": 0,
    }

    nodes = data["nodes"]
    edges = data["edges"]
    assert len(nodes) == 94
    assert len(edges) == 750
    node_ids = [node["id"] for node in nodes]
    assert node_ids == sorted(node_ids)
    assert len(node_ids) == len(set(node_ids))
    for node in nodes:
        assert {
            "id",
            "title",
            "year",
            "doi",
            "authors",
            "abstract",
            "corpus",
            "modality",
            "citations",
            "centrality",
            "links",
            "metadata",
            "eligibility",
            "toolkit",
            "scope",
            "network",
            "layouts",
        }.issubset(node)

    source = _load_source()
    assert source["schema"] == "pps-publication-citation-source.v1"
    assert len(source["nodes"]) == 1712
    assert len(source["edges"]) == 10109
    source_by_id = {node["id"]: node for node in source["nodes"]}
    records_by_doi = _coverage_records_by_doi()
    expected_nodes = sorted(
        (
            node
            for node in source["nodes"]
            if node["corpus"]["documentRole"] != "review"
            and _has_verified_doi_url(node)
            and _has_citation_metadata(node)
            and (
                node["modality"]["audiotactile"]["verified"]
                or any(
                    _record_is_in_scope(record)
                    for record in records_by_doi.get(_normalize_doi(node["doi"]), [])
                )
            )
        ),
        key=lambda node: node["id"],
    )
    assert len(expected_nodes) == 94
    assert node_ids == [node["id"] for node in expected_nodes]

    expected_later_dois = {
        "10.1016/j.neuroimage.2012.06.063",
        "10.1016/j.neuropsychologia.2014.09.043",
        "10.1016/j.cortex.2017.08.033",
        "10.1109/whc.2017.7989970",
    }
    actual_later_dois = {
        node["doi"]
        for node in nodes
        if node["scope"]["provenance"] == "later_exact_doi_audit"
    }
    assert actual_later_dois == expected_later_dois
    assert Counter(node["scope"]["provenance"] for node in nodes) == {
        "legacy_confirmed": 90,
        "later_exact_doi_audit": 4,
    }
    assert Counter(node["toolkit"]["status"] for node in nodes) == {
        "runnable": 15,
        "supported_incomplete": 49,
        "not_assessed": 29,
        "adjacent_scope_conflict": 1,
    }
    assert Counter(node["corpus"]["documentRole"] for node in nodes) == {
        "empirical": 62,
        "clinical_empirical": 3,
        "conference_empirical": 1,
        "empirical_meta_analysis": 1,
        "empirical_model": 2,
        "empirical_template": 1,
        "methods": 7,
        "methods_empirical": 2,
        "model": 4,
        "unknown": 11,
    }

    for node in nodes:
        assert node["corpus"]["documentRole"] != "review"
        assert _has_verified_doi_url(node)
        assert _has_citation_metadata(node)
        assert node["eligibility"] == {
            "verifiedDoiUrl": True,
            "citationMetadataAvailable": True,
            "citationMetadataProviders": _citation_metadata_providers(node),
        }
        source_node = source_by_id[node["id"]]
        expected_provenance = (
            "legacy_confirmed"
            if source_node["modality"]["audiotactile"]["verified"]
            else "later_exact_doi_audit"
        )
        assert node["scope"]["provenance"] == expected_provenance
        assert node["citations"] == source_node["citations"]
        assert node["centrality"] == source_node["centrality"]

        source_records = records_by_doi.get(_normalize_doi(node["doi"]), [])
        joined_records = node["toolkit"]["records"]
        assert [record["recordId"] for record in joined_records] == sorted(
            record["record_id"] for record in source_records
        )
        assert all(
            record["inScope"]
            == (record["coverageCategory"] != "adjacent_out_of_scope")
            for record in joined_records
        )
        assert node["toolkit"]["inScopeRecordCount"] == sum(
            record["inScope"] for record in joined_records
        )
        assert node["toolkit"]["status"] == _expected_toolkit_status(source_records)

    toolkit_records = [record for node in nodes for record in node["toolkit"]["records"]]
    assert len(toolkit_records) == 69
    assert sum(record["inScope"] for record in toolkit_records) == 68
    assert sum(record["inScope"] and record["recreatable"] for record in toolkit_records) == 17
    assert sum(record["manualReview"] is not None for record in toolkit_records) == 24
    assert sum(
        any(record["manualReview"] is not None for record in node["toolkit"]["records"])
        for node in nodes
    ) == 21
    assert Counter(node["abstract"]["status"] for node in nodes) == {
        "available": 37,
        "source_link_only": 48,
        "not_available": 9,
    }

    assert data["facets"]["scopeProvenance"] == {
        "later_exact_doi_audit": 4,
        "legacy_confirmed": 90,
    }
    assert data["facets"]["toolkitStatuses"] == {
        "adjacent_scope_conflict": 1,
        "not_assessed": 29,
        "runnable": 15,
        "supported_incomplete": 49,
    }
    assert data["facets"]["edgeProvenance"]["openalex_live_20260808"] == 127
    assert data["facets"]["edgeProvenance"]["primary_source_audit_20260808"] == 52
    assert data["citationOverlays"] == [
        {
            "id": "openalex-audiotactile-20260808",
            "capturedOn": "2026-08-08",
            "provider": "OpenAlex",
            "edgeProvenance": "openalex_live_20260808",
            "sourceEdges": 127,
            "addedEdges": 127,
            "scope": _load_citation_overlay()["scope"],
        },
        {
            "id": "primary-source-isolate-audit-20260808",
            "capturedOn": "2026-08-08",
            "provider": "Primary-source reference-list audit",
            "edgeProvenance": "primary_source_audit_20260808",
            "sourceEdges": 60,
            "addedEdges": 52,
            "scope": _load_primary_source_citation_overlay()["scope"],
        },
    ]
    assert "readiness is an encoding, never an inclusion gate" in data["methodology"]["selection"]
    assert "exact-DOI resolver audit confirms every DOI-bearing candidate" in data["methodology"]["selection"]
    assert "finite citation count, including a valid count of zero" in data["methodology"]["selection"]
    assert data["methodology"]["edgeDirection"] == "source publication cites target publication"
    assert "normalized DOI only" in data["methodology"]["toolkitJoin"]


def test_publication_network_edges_are_the_complete_tracked_snapshot_overlay_union() -> None:
    data = _load_network()
    source = _load_source()
    overlay = _load_citation_overlay()
    primary_overlay = _load_primary_source_citation_overlay()
    nodes = data["nodes"]
    edges = data["edges"]
    node_ids = [node["id"] for node in nodes]
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    selected_ids = set(node_ids)
    records_by_doi = _coverage_records_by_doi()
    candidate_ids = {
        node["id"]
        for node in source["nodes"]
        if node["corpus"]["documentRole"] != "review"
        and (
            node["modality"]["audiotactile"]["verified"]
            or any(
                _record_is_in_scope(record)
                for record in records_by_doi.get(_normalize_doi(node["doi"]), [])
            )
        )
    }

    expected_snapshot_edges = {
        (
            node_index[edge["source"]],
            node_index[edge["target"]],
            edge["provenance"],
        )
        for edge in source["edges"]
        if edge["source"] in selected_ids and edge["target"] in selected_ids
    }
    assert overlay["schema"] == "pps-publication-citation-overlay.v1"
    assert overlay["scope"]["nodeCount"] == 97
    assert overlay["scope"]["snapshotEdges"] == 571
    assert overlay["scope"]["overlayEdges"] == 127
    assert overlay["scope"]["baseUnionEdges"] == 571
    assert overlay["scope"]["expectedUnionEdges"] == 698
    overlay_pairs = [tuple(pair) for pair in overlay["edges"]]
    assert len(overlay_pairs) == len(set(overlay_pairs)) == 127
    assert all(source_id in candidate_ids and target_id in candidate_ids
               for source_id, target_id in overlay_pairs)
    expected_overlay_edges = {
        (
            node_index[source_id],
            node_index[target_id],
            overlay["edgeProvenance"],
        )
        for source_id, target_id in overlay_pairs
        if source_id in selected_ids and target_id in selected_ids
    }
    snapshot_pairs = {(source_index, target_index) for source_index, target_index, _ in expected_snapshot_edges}
    assert not snapshot_pairs.intersection(
        (source_index, target_index)
        for source_index, target_index, _ in expected_overlay_edges
    )
    assert primary_overlay["schema"] == "pps-publication-citation-overlay.v1"
    assert primary_overlay["scope"] == {
        "networkSchema": "pps-publication-citation-network.v3",
        "nodeCount": 97,
        "auditedSourceNodes": 6,
        "baseUnionEdges": 698,
        "overlayEdges": 60,
        "expectedUnionEdges": 758,
    }
    primary_pairs = [tuple(pair) for pair in primary_overlay["edges"]]
    assert len(primary_pairs) == len(set(primary_pairs)) == 60
    assert all(source_id in candidate_ids and target_id in candidate_ids
               for source_id, target_id in primary_pairs)
    expected_primary_edges = {
        (
            node_index[source_id],
            node_index[target_id],
            primary_overlay["edgeProvenance"],
        )
        for source_id, target_id in primary_pairs
        if source_id in selected_ids and target_id in selected_ids
    }
    earlier_pairs = snapshot_pairs | {
        (source_index, target_index)
        for source_index, target_index, _ in expected_overlay_edges
    }
    assert not earlier_pairs.intersection(
        (source_index, target_index)
        for source_index, target_index, _ in expected_primary_edges
    )
    assert sum(source["verifiedEdges"] for source in primary_overlay["sources"]) == 60
    assert {source["nodeId"] for source in primary_overlay["sources"]} == {
        "doi:10.1101/2024.10.25.619776",
        "doi:10.17605/osf.io/73x59",
        "doi:10.31234/osf.io/etvb6_v1",
        "doi:10.61782/fa.2025.0866",
        "s2:a59674e92994a1800d2b458998ca84ec8173bff1",
        "s2:dc9efaa028822672316fdac32cf9b5c66e656594",
    }
    expected_edges = expected_snapshot_edges | expected_overlay_edges | expected_primary_edges
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
    assert len(expected_snapshot_edges) == 571
    assert len(expected_primary_edges) == 52
    assert len(expected_edges) == 750
    assert actual_edges == expected_edges

    adjacency = _weak_adjacency(len(nodes), edges)
    weak_pairs = {
        (min(source, target), max(source, target))
        for source, target, _provenance in edges
    }
    assert len(weak_pairs) == 747
    components = _weak_components(adjacency)
    assert [len(component) for component in components] == [91] + [1] * 3
    assert sum(bool(neighbours) for neighbours in adjacency) == 91
    assert sum(not neighbours for neighbours in adjacency) == 3
    assert data["counts"]["connectedNodes"] == 91
    assert data["counts"]["isolatedNodes"] == 3
    assert data["counts"]["weakComponents"] == 4

    incoming = [0] * len(nodes)
    outgoing = [0] * len(nodes)
    for source, target, _provenance in edges:
        outgoing[source] += 1
        incoming[target] += 1
    for index, node in enumerate(nodes):
        assert node["network"]["inDegree"] == incoming[index]
        assert node["network"]["outDegree"] == outgoing[index]
        assert node["network"]["weakDegree"] == len(adjacency[index])
        assert node["network"]["isolated"] == (not adjacency[index])
    assert math.isclose(
        sum(node["network"]["pageRank"] for node in nodes),
        1,
        abs_tol=1e-8,
    )

    radii_by_indegree: dict[int, set[float]] = {}
    for node in nodes:
        radii_by_indegree.setdefault(node["network"]["inDegree"], set()).add(
            node["network"]["radius"]
        )
    assert all(len(radii) == 1 for radii in radii_by_indegree.values())
    ordered_radii = [next(iter(radii_by_indegree[value])) for value in sorted(radii_by_indegree)]
    assert ordered_radii == sorted(ordered_radii)
    assert min(ordered_radii) == 0.009
    assert max(ordered_radii) == 0.024

    log_incoming = [math.log1p(value) for value in incoming]
    minimum_log = min(log_incoming)
    log_range = max(log_incoming) - minimum_log
    minimum_area = 0.009 ** 2
    area_range = 0.024 ** 2 - minimum_area
    for index, node in enumerate(nodes):
        normalized = (
            (log_incoming[index] - minimum_log) / log_range
            if log_range > 0
            else 0
        )
        expected_radius = math.sqrt(minimum_area + area_range * normalized)
        assert math.isclose(
            node["network"]["radius"],
            expected_radius,
            abs_tol=1.1e-6,
        )


def test_publication_network_layouts_are_continuous_collision_free_and_meaningful() -> None:
    data = _load_network()
    nodes = data["nodes"]
    edges = data["edges"]
    square = data["layoutBounds"]["square"]
    assert square == {
        "minX": 0,
        "maxX": 1,
        "minY": 0,
        "maxY": 1,
        "nodeExtentMargin": 0.045,
        "minimumNodeRadius": 0.009,
        "maximumNodeRadius": 0.024,
        "requiredNodeClearance": 0.015,
    }

    for layout_name in ("topology", "timeline"):
        positions = [node["layouts"][layout_name] for node in nodes]
        assert all(set(position) == {"x", "y"} for position in positions)
        assert all(
            math.isfinite(position[axis]) and 0 <= position[axis] <= 1
            for position in positions
            for axis in ("x", "y")
        )
        assert len({(position["x"], position["y"]) for position in positions}) == 94
        assert len({round(position["x"], 4) for position in positions}) >= 85
        assert len({round(position["y"], 4) for position in positions}) >= 85

        minimum_clearance = math.inf
        for index, left in enumerate(positions):
            radius = nodes[index]["network"]["radius"]
            assert left["x"] - radius >= square["nodeExtentMargin"] - 2e-6
            assert left["x"] + radius <= 1 - square["nodeExtentMargin"] + 2e-6
            assert left["y"] - radius >= square["nodeExtentMargin"] - 2e-6
            assert left["y"] + radius <= 1 - square["nodeExtentMargin"] + 2e-6
            for other in range(index + 1, len(positions)):
                right = positions[other]
                distance = math.hypot(left["x"] - right["x"], left["y"] - right["y"])
                clearance = (
                    distance
                    - radius
                    - nodes[other]["network"]["radius"]
                )
                minimum_clearance = min(minimum_clearance, clearance)
                assert clearance >= square["requiredNodeClearance"] - 3e-6
        quality = data["layoutBounds"][layout_name]
        assert quality["clearanceViolations"] == 0
        assert math.isclose(quality["minimumClearance"], minimum_clearance, abs_tol=1e-6)

    topology = [node["layouts"]["topology"] for node in nodes]
    adjacency = _weak_adjacency(len(nodes), edges)
    principal_component = _weak_components(adjacency)[0]
    weak_pairs = {
        (min(source, target), max(source, target))
        for source, target, _provenance in edges
    }
    linked_distances = [
        math.hypot(
            topology[source]["x"] - topology[target]["x"],
            topology[source]["y"] - topology[target]["y"],
        )
        for source, target in weak_pairs
    ]
    principal_non_neighbour_distances = [
        math.hypot(
            topology[left]["x"] - topology[right]["x"],
            topology[left]["y"] - topology[right]["y"],
        )
        for left in sorted(principal_component)
        for right in sorted(principal_component)
        if left < right and (left, right) not in weak_pairs
    ]
    proximity_ratio = _mean(linked_distances) / _mean(principal_non_neighbour_distances)
    assert proximity_ratio < 0.75
    assert math.isclose(
        data["layoutBounds"]["topology"]["edgeToPrincipalNonNeighbourRatio"],
        proximity_ratio,
        abs_tol=1e-6,
    )

    principal_x = [topology[index]["x"] for index in principal_component]
    principal_y = [topology[index]["y"] for index in principal_component]
    span_x = max(principal_x) - min(principal_x)
    span_y = max(principal_y) - min(principal_y)
    assert span_x >= 0.7
    assert span_y >= 0.7
    assert math.isclose(
        data["layoutBounds"]["topology"]["principalComponentSpanX"],
        span_x,
        abs_tol=1e-6,
    )
    assert math.isclose(
        data["layoutBounds"]["topology"]["principalComponentSpanY"],
        span_y,
        abs_tol=1e-6,
    )
    occupied_cells = {
        (min(5, int(topology[index]["x"] * 6)), min(5, int(topology[index]["y"] * 6)))
        for index in principal_component
    }
    assert len(occupied_cells) >= 20
    assert data["layoutBounds"]["topology"]["principalComponentOccupiedGridCells6x6"] == len(occupied_cells)

    nearest_distances = [
        min(
            math.hypot(position["x"] - other["x"], position["y"] - other["y"])
            for other_index, other in enumerate(topology)
            if other_index != index
        )
        for index, position in enumerate(topology)
    ]
    nearest_median = _median(nearest_distances)
    assert nearest_median >= 0.055
    assert math.isclose(
        data["layoutBounds"]["topology"]["medianNearestNeighbourDistance"],
        nearest_median,
        abs_tol=1e-6,
    )
    isolated_near_boundary = sum(
        not adjacency[index]
        and min(position["x"], 1 - position["x"], position["y"], 1 - position["y"]) < 0.09
        for index, position in enumerate(topology)
    )
    assert isolated_near_boundary <= 3
    assert data["layoutBounds"]["topology"]["isolatedNodesNearBoundary"] == isolated_near_boundary

    timeline_entries = [
        (node["year"], node["layouts"]["timeline"]["x"])
        for node in nodes
        if isinstance(node["year"], int)
    ]
    year_x_correlation = _spearman(
        [float(year) for year, _x in timeline_entries],
        [x for _year, x in timeline_entries],
    )
    assert year_x_correlation > 0.9
    yearly_medians = [
        _median([x for year, x in timeline_entries if year == current_year])
        for current_year in sorted({year for year, _x in timeline_entries})
    ]
    assert yearly_medians == sorted(yearly_medians)
    unknown_positions = [
        node["layouts"]["timeline"]["x"]
        for node in nodes
        if not isinstance(node["year"], int)
    ]
    assert unknown_positions == []
    assert data["layoutBounds"]["timeline"]["minYear"] == 2001
    assert data["layoutBounds"]["timeline"]["maxYear"] == 2026
    assert data["layoutBounds"]["timeline"]["nodeOrder"] == [
        "year on horizontal axis",
        "unknown year last",
        "stable ID jitter",
    ]


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
    rebuilt = tmp_path / "publication_network.v3.json"
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
    assert report["schema"] == "pps-publication-citation-network.v3"
    assert report["sourceCounts"] == _load_network()["sourceCounts"]
    assert report["counts"] == _load_network()["counts"]
    assert rebuilt.read_bytes() == NETWORK_ASSET.read_bytes()
