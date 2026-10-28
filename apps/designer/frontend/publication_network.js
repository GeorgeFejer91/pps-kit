const DATA_URL = new URL("./publication_network.v3.json", import.meta.url);
const REVIEWS_URL = new URL("./publication_study_reviews.v1.json", import.meta.url);
const RESULT_PAGE_SIZE = 40;
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  for (const [name, value] of Object.entries(options.attributes || {})) {
    if (value !== null && value !== undefined && value !== false) node.setAttribute(name, String(value));
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child) node.append(child);
  }
  return node;
}

function svgElement(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NAMESPACE, tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value !== null && value !== undefined && value !== false) node.setAttribute(name, String(value));
  }
  return node;
}

function compactNumber(value, digits = 3) {
  const number = Number(value || 0);
  if (number >= 1000) return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(number);
  if (number > 0 && number < 0.001) return number.toExponential(2);
  return number.toLocaleString("en", { maximumFractionDigits: digits });
}

function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function metricValue(node, metric) {
  if (metric === "networkReceived") return Number(node.network?.inDegree || 0);
  if (metric === "networkPageRank") return Number(node.network?.pageRank || 0);
  if (metric === "pageRank") return Number(node.centrality?.pageRank || 0);
  if (metric === "betweennessApprox") return Number(node.centrality?.betweennessApprox || 0);
  if (metric === "externalMax") return Number(node.citations?.externalMax || 0);
  if (metric === "uniform") return 1;
  return Number(node.citations?.withinCorpusReceived || 0);
}

function toolkitStatus(node) {
  return node.toolkit?.status || "not_assessed";
}

function toolkitStatusLabel(node) {
  const count = node.studyReview?.templateIds.length || 0;
  return count ? `${count} linked Toolkit template${count === 1 ? "" : "s"}` : "No linked Toolkit template";
}

function reviewPriority(node) {
  const status = toolkitStatus(node);
  if (status === "not_assessed") return 4;
  if (status === "adjacent_scope_conflict") return 3;
  if (status === "supported_incomplete") return 2;
  return 1;
}

function hasTemplate(node) {
  return Boolean(node.studyReview?.templateIds.length);
}

export function publicationMatches(node, query) {
  const normalize = value => String(value || "").normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
  const terms = normalize(query).replace(/^https?:\/\/(?:dx\.)?doi\.org\//, "").replace(/^doi:\s*/, "").trim().split(/\s+/).filter(Boolean);
  const text = normalize([node.title, ...(node.authors || []), node.doi, node.year].join(" "));
  return terms.every(term => text.includes(term));
}

export function evidenceSummary(counts = {}) {
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  return `${counts.reported_complete || 0} reported complete · ${counts.derived_complete || 0} derived complete · ${total} contracts`;
}

export function studyDisplayLabel(study) {
  const experiment = typeof study.experimentLabel === "string" ? study.experimentLabel.trim() : "";
  return experiment || study.label || "Study details";
}

export function publicationInclusionBasis(node) {
  const basis = typeof node.scope?.basis === "string" ? node.scope.basis.trim() : "";
  return basis || "This record is included in the frozen publication map. Membership does not establish direct audiotactile task eligibility.";
}

function contractStatusDescription(status, legend = {}) {
  if (status === "partial") return "Some required stimulus, timing, or trial-structure details are missing or unresolved.";
  return legend[status] || "Evidence status unavailable.";
}

export function inventoryAuditSummary(audit) {
  if (!audit) return "Methods inventory audit is unavailable in this snapshot.";
  const projectLineage = audit.projectLineageReviews > 0 ? ` · ${audit.projectLineageReviews} project lineage reviews` : "";
  return `${audit.registeredInventories} of ${audit.publications} inventories registered · ${audit.methodsReviewedInventories} Methods inventories reviewed${projectLineage} · ${audit.auditedAccessBlockers} documented access blockers · ${audit.inventoryAndContractsAudited} inventory and contract audits complete · ${audit.remainingInventoryOrContractAudit} remaining`;
}

export function inventoryEvidenceLabel(status) {
  return {
    primary_methods_reviewed: "Primary Methods reviewed",
    primary_project_lineage_reviewed: "Primary project lineage reviewed",
    retained_primary_methods_review: "Retained primary Methods review",
    author_version_methods_reviewed_final_comparison_pending: "Author-version Methods reviewed; final-version comparison pending",
    abstract_or_metadata_inventory: "Abstract or metadata only; Methods inventory unresolved",
    partial_methods_inventory: "Partial Methods inventory; boundaries unresolved",
    audited_source_access_gap: "Documented source-access blocker; Methods unavailable",
    not_registered: "No registered inventory",
    inventory_evidence_not_classified: "Inventory evidence not classified",
  }[status] || "Inventory evidence unavailable in this snapshot";
}

function makeBadge(text, className = "") {
  return element("span", { className: `publication-network-badge ${className}`.trim(), text, attributes: { "data-pretext": true } });
}

function makeSection(title, children = []) {
  return element("section", { className: "publication-network-detail-section" }, [
    element("h4", { text: title, attributes: { "data-pretext": true } }),
    ...children,
  ]);
}

function safeExternalLink(label, href) {
  if (!href || !/^https?:\/\//i.test(href)) return null;
  return element("a", {
    text: label,
    attributes: { href, target: "_blank", rel: "noopener noreferrer" },
  });
}

function designerTemplateUrl(templateId) {
  const url = new URL(window.location.href);
  url.searchParams.set("page", "toolkit");
  url.searchParams.set("template", templateId);
  for (const key of ["publication", "study", "publicationQuery"]) url.searchParams.delete(key);
  url.hash = "study-segment";
  return url.href;
}

function designerTemplateLink(templateId) {
  return element("a", {
    text: titleCase(templateId),
    attributes: {
      href: designerTemplateUrl(templateId),
      target: "_blank",
      rel: "noopener noreferrer",
      title: `Open ${titleCase(templateId)} in Experiment Designer`,
      "data-open-designer-template": templateId,
      "data-pretext": true,
    },
  });
}

export async function initializePublicationNetwork(root) {
  if (!root || root.dataset.publicationNetworkState === "ready") return;

  const controls = {
    layout: [...root.querySelectorAll('input[name="publication-network-layout"]')],
    resultsSort: root.querySelector("#publication-network-results-sort"),
    search: root.querySelector("#publication-network-search"),
  };
  const shell = root.querySelector(".publication-network-shell");
  const workspace = root.querySelector("#publication-network-workspace");
  const graph = root.querySelector("#publication-network-graph");
  const stage = root.querySelector("#publication-network-stage");
  const loading = root.querySelector("#publication-network-loading");
  const tooltip = root.querySelector("#publication-network-tooltip");
  const status = root.querySelector("#publication-network-status");
  const resultCount = root.querySelector("#publication-network-results-count");
  const resultList = root.querySelector("#publication-network-results");
  const resultMore = root.querySelector("#publication-network-results-more");
  const detail = root.querySelector("#publication-network-detail");
  const detailTitle = root.querySelector("#publication-network-detail-title");
  const detailKicker = root.querySelector("#publication-network-detail-kicker");
  const detailBody = root.querySelector("#publication-network-detail-body");
  const detailClose = root.querySelector("#publication-network-detail-close");
  const fullscreenButton = root.querySelector("#publication-network-fullscreen");
  if (!shell || !workspace || !graph || !stage) {
    throw new Error("Publication-network SVG is unavailable.");
  }

  const [response, reviewResponse] = await Promise.all([fetch(DATA_URL), fetch(REVIEWS_URL)]);
  if (!response.ok || !reviewResponse.ok) throw new Error(`Publication data request failed (${response.status}, ${reviewResponse.status}).`);
  const [data, reviews] = await Promise.all([response.json(), reviewResponse.json()]);
  if (data.schema !== "pps-publication-citation-network.v3") {
    throw new Error(`Unsupported publication-network schema: ${data.schema || "missing"}`);
  }

  if (reviews.schema !== "pps-publication-study-reviews.v1") throw new Error("Unsupported study-review schema.");
  const reviewByPublication = new Map(reviews.publications.map(review => [review.networkNodeId, review]));
  const studyById = new Map(reviews.studies.map(study => [study.studyRowId, study]));
  if (data.nodes.some(node => !reviewByPublication.has(node.id))
    || reviews.publications.some(review => review.studyIds.some(id => !studyById.has(id)))) {
    throw new Error("Publication and study-review snapshots do not match.");
  }
  const nodes = data.nodes.map(node => ({ ...node, studyReview: reviewByPublication.get(node.id) }));
  const edges = data.edges;
  const incoming = Array.from({ length: nodes.length }, () => []);
  const outgoing = Array.from({ length: nodes.length }, () => []);
  for (const [source, target] of edges) {
    outgoing[source].push(target);
    incoming[target].push(source);
  }
  const allIndices = nodes.map((_, index) => index);
  const state = {
    layout: "topology",
    visible: allIndices,
    visibleSet: new Set(allIndices),
    selected: null,
    hovered: null,
    resultLimit: RESULT_PAGE_SIZE,
    lastFocus: graph,
    lastFocusNode: null,
    redrawPending: false,
    projected: new Map(),
    overlapCount: 0,
  };
  const initialUrl = new URL(window.location.href);
  controls.search.value = initialUrl.searchParams.get("publicationQuery") || "";
  root.querySelector("#publication-network-size-note").textContent = `Circle area reflects incoming citations in this ${nodes.length}-paper map. Size and position are navigation aids, not study-quality scores.`;
  graph.setAttribute("aria-label", `Citation network of ${nodes.length} publications. Search or use the publication list for keyboard access; arrow keys move between papers.`);

  function updateLink(studyId = "") {
    const url = new URL(window.location.href);
    url.searchParams.set("page", "documentation");
    if (state.selected === null) url.searchParams.delete("publication");
    else url.searchParams.set("publication", nodes[state.selected].id);
    if (studyId) url.searchParams.set("study", studyId); else url.searchParams.delete("study");
    const query = controls.search.value.trim();
    if (query) url.searchParams.set("publicationQuery", query); else url.searchParams.delete("publicationQuery");
    history.replaceState(null, "", url);
  }

  function positionFor(index) {
    return nodes[index].layouts[state.layout] || nodes[index].layouts.topology;
  }

  function graphGeometry() {
    const rect = graph.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    const padding = Math.max(18, Math.min(42, Math.min(width, height) * 0.055));
    const plotWidth = Math.max(1, width - padding * 2);
    const plotHeight = Math.max(1, height - padding * 2);
    return {
      width,
      height,
      plotWidth,
      plotHeight,
      plotScale: Math.min(plotWidth, plotHeight),
      originX: padding,
      originY: padding,
    };
  }

  function screenPoint(index, geometry) {
    const position = positionFor(index);
    return {
      x: geometry.originX + position.x * geometry.plotWidth,
      y: geometry.originY + position.y * geometry.plotHeight,
    };
  }

  function radiusFor(index, geometry) {
    return geometry.plotScale * Number(nodes[index].network?.radius || 0.009);
  }

  function overlapCount(projected, geometry) {
    let count = 0;
    for (let left = 0; left < state.visible.length; left += 1) {
      const leftIndex = state.visible[left];
      const leftPoint = projected.get(leftIndex);
      for (let right = left + 1; right < state.visible.length; right += 1) {
        const rightIndex = state.visible[right];
        const rightPoint = projected.get(rightIndex);
        const minimum = radiusFor(leftIndex, geometry) + radiusFor(rightIndex, geometry) + 0.75;
        if (Math.hypot(leftPoint.x - rightPoint.x, leftPoint.y - rightPoint.y) + 0.25 < minimum) count += 1;
      }
    }
    return count;
  }

  function requestDraw() {
    if (state.redrawPending) return;
    state.redrawPending = true;
    requestAnimationFrame(() => {
      state.redrawPending = false;
      renderGraph();
    });
  }

  function resizeGraph() {
    if (document.fullscreenElement === shell) {
      const scale = shell.getBoundingClientRect().width / parseFloat(getComputedStyle(shell).width) || 1;
      const summary = shell.querySelector(".publication-network-summary-row");
      const search = shell.querySelector(".publication-network-search-row");
      const padding = getComputedStyle(workspace);
      const remaining = window.innerHeight / scale - summary.offsetHeight - search.offsetHeight
        - parseFloat(padding.paddingTop) - parseFloat(padding.paddingBottom);
      // The graph owns the remaining viewport. Its long result/detail documents
      // continue below it; they must not inflate this bounded visual viewport.
      const size = `${Math.max(120, Math.floor(remaining))}px`;
      if (shell.style.getPropertyValue("--network-fullscreen-graph-size") !== size) shell.style.setProperty("--network-fullscreen-graph-size", size);
    }
    requestDraw();
  }

  const timelineLayer = svgElement("g", { class: "publication-network-timeline" });
  const edgeLayer = svgElement("g", { class: "publication-network-edges" });
  const nodeLayer = svgElement("g", { class: "publication-network-nodes" });
  graph.replaceChildren(timelineLayer, edgeLayer, nodeLayer);

  const edgeElements = edges.map(() => {
    const group = svgElement("g", { class: "publication-network-edge" });
    const line = svgElement("line", { class: "publication-network-edge-line" });
    const arrow = svgElement("polygon", { class: "publication-network-edge-arrow" });
    group.append(line, arrow);
    edgeLayer.append(group);
    return { group, line, arrow };
  });

  const orderedNodeIndices = [...state.visible].sort((left, right) =>
    Number(nodes[left].network?.radius || 0.009) - Number(nodes[right].network?.radius || 0.009));
  const nodeElements = new Map(orderedNodeIndices.map((index) => {
    const group = svgElement("g", {
      class: "publication-network-node-mark",
      "data-node-index": index,
    });
    const selection = svgElement("circle", { class: "publication-network-node-selection" });
    const circle = svgElement("circle", { class: "publication-network-node" });
    group.append(selection, circle);
    nodeLayer.append(group);
    return [index, { group, selection, circle }];
  }));

  function renderTimelineLabels(projected, geometry) {
    timelineLayer.replaceChildren();
    if (state.layout !== "timeline") return;
    const years = [...new Set(state.visible.map((index) => nodes[index].year).filter(Number.isFinite))].sort((a, b) => a - b);
    if (!years.length) return;
    const guideYears = years.length <= 5
      ? years
      : [0, 0.25, 0.5, 0.75, 1].map((fraction) => years[Math.round((years.length - 1) * fraction)]);
    for (const year of new Set(guideYears)) {
      const matches = state.visible.filter((index) => nodes[index].year === year);
      const x = matches.reduce((sum, index) => sum + projected.get(index).x, 0) / matches.length;
      timelineLayer.append(
        svgElement("line", {
          class: "publication-network-timeline-guide",
          x1: x,
          y1: geometry.originY,
          x2: x,
          y2: geometry.originY + geometry.plotHeight,
        }),
        svgElement("text", {
          class: "publication-network-timeline-label",
          x,
          y: Math.max(12, geometry.originY - 10),
          "font-size": geometry.plotScale < 420 ? 8 : 10,
        }),
      );
      timelineLayer.lastElementChild.textContent = String(year);
    }
  }

  function selectedEdgeRelation(source, target) {
    if (state.selected === target) return "incoming";
    if (state.selected === source) return "outgoing";
    return "";
  }

  function renderCitationEdge(edgeIndex, source, target, projected, geometry) {
    const { group, line, arrow } = edgeElements[edgeIndex];
    const from = projected.get(source);
    const to = projected.get(target);
    const relation = selectedEdgeRelation(source, target);
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.max(1, Math.hypot(dx, dy));
    const ux = dx / length;
    const uy = dy / length;
    const startInset = relation ? radiusFor(source, geometry) + 1 : 0;
    const endInset = relation ? radiusFor(target, geometry) + 3.5 : 0;
    const startX = from.x + ux * startInset;
    const startY = from.y + uy * startInset;
    const endX = to.x - ux * endInset;
    const endY = to.y - uy * endInset;
    group.setAttribute("class", `publication-network-edge${relation ? ` ${relation}` : ""}`);
    line.setAttribute("x1", String(startX));
    line.setAttribute("y1", String(startY));
    line.setAttribute("x2", String(endX));
    line.setAttribute("y2", String(endY));
    if (!relation) {
      arrow.removeAttribute("points");
      return relation;
    }
    const arrowSize = 4.5;
    arrow.setAttribute("points", [
      `${endX},${endY}`,
      `${endX - ux * arrowSize - uy * arrowSize * 0.58},${endY - uy * arrowSize + ux * arrowSize * 0.58}`,
      `${endX - ux * arrowSize + uy * arrowSize * 0.58},${endY - uy * arrowSize - ux * arrowSize * 0.58}`,
    ].join(" "));
    return relation;
  }

  function renderGraph() {
    const geometry = graphGeometry();
    const { width, height } = geometry;
    graph.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const projected = new Map(state.visible.map((index) => [index, screenPoint(index, geometry)]));
    state.projected = projected;
    state.overlapCount = overlapCount(projected, geometry);
    root.dataset.publicationNetworkOverlaps = String(state.overlapCount);
    renderTimelineLabels(projected, geometry);

    const selectedEdgeGroups = [];
    for (let edgeIndex = 0; edgeIndex < edges.length; edgeIndex += 1) {
      const [source, target] = edges[edgeIndex];
      const visible = state.visibleSet.has(source) && state.visibleSet.has(target);
      edgeElements[edgeIndex].group.style.display = visible ? "" : "none";
      if (!visible) continue;
      if (renderCitationEdge(edgeIndex, source, target, projected, geometry)) {
        selectedEdgeGroups.push(edgeElements[edgeIndex].group);
      }
    }
    edgeLayer.append(...selectedEdgeGroups);

    for (const index of orderedNodeIndices) {
      const point = projected.get(index);
      const radius = radiusFor(index, geometry);
      const implemented = hasTemplate(nodes[index]);
      const { group, selection, circle } = nodeElements.get(index);
      group.style.display = point ? "" : "none";
      if (!point) continue;
      group.setAttribute("class", [
        "publication-network-node-mark",
        implemented ? "implemented" : "not-implemented",
        state.hovered === index ? "hovered" : "",
        state.selected === index ? "selected" : "",
      ].filter(Boolean).join(" "));
      for (const node of [selection, circle]) {
        node.setAttribute("cx", String(point.x));
        node.setAttribute("cy", String(point.y));
      }
      selection.setAttribute("r", String(radius + 4));
      circle.setAttribute("r", String(radius));
    }
  }

  function hitTest(clientX, clientY) {
    const rect = graph.getBoundingClientRect();
    const geometry = graphGeometry();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let best = null;
    let bestDistance = Infinity;
    for (const index of state.visible) {
      const point = state.projected.get(index) || screenPoint(index, geometry);
      const distance = Math.hypot(point.x - x, point.y - y);
      if (distance <= Math.max(12, radiusFor(index, geometry) + 6) && distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    }
    return best;
  }

  function setTooltip(index, clientX, clientY) {
    if (index === null) {
      tooltip.hidden = true;
      tooltip.replaceChildren();
      return;
    }
    const node = nodes[index];
    tooltip.replaceChildren(
      element("strong", { text: node.title }),
      element("span", { text: `${node.year || "Year unavailable"} · ${node.authors?.join(", ") || "Authors unavailable"}` }),
      element("span", {
        text: `${node.network?.inDegree || 0} citation${node.network?.inDegree === 1 ? "" : "s"} received in this map · ${toolkitStatusLabel(node)}`,
      }),
    );
    tooltip.hidden = false;
    tooltip.dataset.inline = "false";
    const stageRect = stage.getBoundingClientRect();
    const scale = stageRect.width / parseFloat(getComputedStyle(stage).width) || 1;
    // Measure the actual wrapped text, including user zoom and spacing. A long
    // summary joins document flow below the graph instead of clipping in it.
    tooltip.dataset.inline = String(tooltip.offsetHeight > stage.clientHeight - 24);
    tooltip.style.left = `${Math.max(12, Math.min(stage.clientWidth - tooltip.offsetWidth - 12, (clientX - stageRect.left) / scale + 14))}px`;
    tooltip.style.top = `${Math.max(12, Math.min(stage.clientHeight - tooltip.offsetHeight - 12, (clientY - stageRect.top) / scale + 14))}px`;
  }

  function currentLayout() {
    return controls.layout.find((input) => input.checked)?.value || "topology";
  }

  function sortResults(indices) {
    const metric = controls.resultsSort.value;
    return [...indices].sort((left, right) => {
      if (metric === "year-desc") return (nodes[right].year || 0) - (nodes[left].year || 0) || nodes[left].title.localeCompare(nodes[right].title);
      if (metric === "year-asc") return (nodes[left].year || 9999) - (nodes[right].year || 9999) || nodes[left].title.localeCompare(nodes[right].title);
      if (metric === "title") return nodes[left].title.localeCompare(nodes[right].title);
      if (metric === "review-priority") return reviewPriority(nodes[right]) - reviewPriority(nodes[left])
        || metricValue(nodes[right], "networkReceived") - metricValue(nodes[left], "networkReceived")
        || nodes[left].title.localeCompare(nodes[right].title);
      return metricValue(nodes[right], metric) - metricValue(nodes[left], metric) || nodes[left].title.localeCompare(nodes[right].title);
    });
  }

  function renderResults() {
    const sorted = sortResults(state.visible);
    const shown = sorted.slice(0, state.resultLimit);
    resultList.replaceChildren(...shown.map((index) => {
      const node = nodes[index];
      const button = element("button", {
        className: "publication-network-result-button",
        attributes: {
          type: "button",
          "data-node-index": index,
          "aria-current": state.selected === index ? "true" : "false",
        },
      }, [
        element("strong", { text: node.title }),
        element("span", {
          text: `${node.year || "n.d."} · ${node.authors?.join(", ") || "Authors unavailable"} · ${node.network?.inDegree || 0} citation${node.network?.inDegree === 1 ? "" : "s"} received here · ${toolkitStatusLabel(node)}`,
        }),
      ]);
      button.addEventListener("click", () => selectNode(index, button));
      return element("li", {}, button);
    }));
    resultCount.textContent = `${sorted.length.toLocaleString()} paper${sorted.length === 1 ? "" : "s"}`;
    resultMore.hidden = shown.length >= sorted.length;
  }

  function updateStatus() {
    const layoutLabel = state.layout === "timeline" ? "publication-year arrangement" : "citation topology";
    const selectedText = state.selected === null
      ? ""
      : ` · selected: ${nodes[state.selected].title} (${incoming[state.selected].length} incoming, ${outgoing[state.selected].length} outgoing)`;
    status.textContent = `${state.visible.length} of ${nodes.length} papers · ${reviews.counts.studies} study records · ${nodes.filter(hasTemplate).length} papers with linked templates · ${edges.length} indexed citations · ${layoutLabel}${selectedText}`;
  }

  function updateSearch({ syncLink = true } = {}) {
    state.visible = allIndices.filter(index => publicationMatches(nodes[index], controls.search.value));
    state.visibleSet = new Set(state.visible);
    state.resultLimit = RESULT_PAGE_SIZE;
    if (state.selected !== null && !state.visibleSet.has(state.selected)) closeDetail({ restoreFocus: false });
    if (controls.search.value.trim()) resultList.closest("details").open = true;
    state.hovered = null;
    tooltip.hidden = true;
    renderResults();
    updateStatus();
    requestDraw();
    if (syncLink) updateLink();
  }

  function updateLayout() {
    state.layout = currentLayout();
    state.resultLimit = RESULT_PAGE_SIZE;
    updateStatus();
    renderResults();
    requestDraw();
  }

  function makeMetricGrid(node) {
    const displayedPublicationCount = nodes.length.toLocaleString();
    const descriptions = [
      ["Citations in this map", node.network?.inDegree || 0, `Incoming links from the ${displayedPublicationCount} displayed publications`],
      ["References in this map", node.network?.outDegree || 0, `Outgoing links to the ${displayedPublicationCount} displayed publications`],
      ["Network PageRank", compactNumber(node.network?.pageRank, 6), "PageRank recalculated only for this displayed network"],
      ["External citations", node.citations.externalMax, "Largest provider count at snapshot time"],
      ["Broad PPS citations", node.citations.withinCorpusReceived, "Incoming links from the broad 1,712-publication source snapshot"],
      ["Broad PPS references", node.citations.withinCorpusReferences, "Outgoing links in the broad source snapshot"],
    ];
    return element("dl", { className: "publication-network-detail-metrics" }, descriptions.map(([label, value, title]) =>
      element("div", {}, [
        element("dt", { text: label, attributes: { title } }),
        element("dd", { text: value }),
      ])));
  }

  function citationList(indices, emptyText) {
    if (!indices.length) return element("p", { className: "publication-network-detail-muted", text: emptyText });
    const sorted = [...indices]
      .sort((left, right) => (nodes[right].network?.inDegree || 0) - (nodes[left].network?.inDegree || 0));
    const summary = element("p", { className: "publication-network-detail-muted" });
    const list = element("ul", { className: "publication-network-citation-list" });
    const more = element("button", { text: "Show more connected papers", attributes: { type: "button" } });
    let shown = 0;
    const appendPage = () => {
      const items = sorted.slice(shown, shown + 24).map((index) => {
        const button = element("button", {
          text: `${nodes[index].title} (${nodes[index].year || "n.d."})`,
          attributes: { type: "button" },
        });
        button.addEventListener("click", () => selectNode(index, button));
        return element("li", {}, button);
      });
      list.append(...items);
      shown += items.length;
      summary.textContent = `${shown} of ${sorted.length} connected papers shown`;
      more.hidden = shown >= sorted.length;
      return items[0]?.querySelector("button");
    };
    more.addEventListener("click", () => appendPage()?.focus());
    appendPage();
    return element("div", {}, [summary, list, more]);
  }

  function studyRecord(study) {
    const details = element("details", { className: "publication-network-parameter-segment",
      attributes: { "data-study-id": study.studyRowId } });
    details.append(element("summary", {}, [
      element("span", { text: studyDisplayLabel(study), attributes: { "data-pretext": true } }),
      element("small", { text: evidenceSummary(study.parameterStatusCounts) }),
    ]));
    const content = element("div", { className: "publication-network-detail-section" }, [
      element("p", { text: `Evidence scope: ${titleCase(study.evidenceScope)} · Native qualification: ${titleCase(study.nativeQualification)}` }),
      element("p", { text: `Study inventory: ${titleCase(study.inventoryStatus || "not_assessed")}` }),
    ]);
    const templateIds = study.templateIds || [];
    content.append(element("p", { className: "publication-network-detail-muted", text: templateIds.length
      ? "Linked preset for this study. Open in Experiment Designer to prepare and preview; review its evidence gaps before adapting it."
      : "No linked Toolkit template for this study." }));
    if (templateIds.length) content.append(element("div", {
      className: "publication-network-detail-links publication-network-template-links",
    }, templateIds.map(designerTemplateLink)));
    for (const contract of study.contracts) {
      const disclosure = element("details", { className: "publication-network-parameter-segment",
        attributes: { "data-contract-key": contract.key } });
      disclosure.append(element("summary", {}, [
        element("span", { text: contract.label, attributes: { "data-pretext": true } }),
        element("small", { text: titleCase(contract.status), attributes: { title: contractStatusDescription(contract.status, reviews.statusLegend) } }),
      ]));
      const fields = element("div", { className: "publication-network-contract-evidence" }, [
        element("p", { text: contractStatusDescription(contract.status, reviews.statusLegend) }),
        element("p", { text: contract.value || "No study-specific value recorded." }),
      ]);
      if (contract.compositeValue) fields.append(element("p", { text: `Combined-record evidence, not a study-specific value: ${contract.compositeValue}` }));
      if (contract.missingComponents.length) fields.append(element("p", { text: `Unresolved components: ${contract.missingComponents.map(titleCase).join(", ")}` }));
      const components = Object.entries(contract.components);
      if (components.length) fields.append(element("ul", { className: "publication-network-parameter-list" }, components.map(([name, component]) => element("li", {}, [
        element("strong", { text: titleCase(name) }),
        element("span", { text: `${titleCase(component.status)} · ${component.value || "No value recorded"}` }),
        component.note ? element("small", { text: component.note }) : null,
      ]))));
      if (contract.evidenceNote) fields.append(element("p", { text: contract.evidenceNote }));
      if (contract.derivationNote) fields.append(element("p", { text: `Derivation: ${contract.derivationNote}` }));
      const location = [contract.pageOrSection, contract.reviewedOn ? `Reviewed ${contract.reviewedOn}` : ""].filter(Boolean).join(" · ");
      if (location) fields.append(element("small", { text: location }));
      if (contract.sourceType) fields.append(element("p", { text: `Review source type: ${titleCase(contract.sourceType)}` }));
      const sources = [
        safeExternalLink("Reviewed source / access record", contract.evidenceSourceUrl),
        safeExternalLink("Publication DOI", contract.sourceUrl),
      ].filter(Boolean);
      if (sources.length) fields.append(element("div", { className: "publication-network-detail-links" }, sources));
      disclosure.append(fields);
      content.append(disclosure);
    }
    details.append(content);
    details.addEventListener("toggle", () => {
      if (details.open && nodes[state.selected]?.id === study.networkNodeId) updateLink(study.studyRowId);
    });
    return details;
  }

  function renderDetail(index) {
    const node = nodes[index];
    const records = node.toolkit?.records || [];
    const review = node.studyReview;
    const role = titleCase(node.corpus?.documentRole || "unclassified publication");
    const provenance = node.scope?.provenance || "legacy_confirmed";
    detailTitle.textContent = node.title;
    detailKicker.textContent = `${node.year || "Year unavailable"} · ${node.venue || "Venue unavailable"}`;
    const badges = [
      makeBadge("Included publication", "publication-network-badge-at"),
      makeBadge(role),
      makeBadge(provenance === "later_exact_doi_audit" ? "Later exact-DOI audit addition" : "Legacy manually confirmed set"),
    ];
    if (records.some((record) => record.manualReview)) badges.push(makeBadge("Manual parameter review"));
    if (node.metadata?.retracted) badges.push(makeBadge("Retracted"));

    const links = [
      safeExternalLink("Open DOI", node.links.doi),
      safeExternalLink("Publication source", node.links.primary && node.links.primary !== node.links.doi ? node.links.primary : ""),
      safeExternalLink("Open-access copy", node.links.openAccess),
    ].filter(Boolean);
    const overview = makeSection("Publication", [
      element("p", { className: "publication-network-byline", text: node.authors?.join(", ") || "Authors unavailable" }),
      element("div", { className: "publication-network-badges" }, badges),
      element("p", { className: "publication-network-detail-muted", text: [node.venue, node.publicationDate || node.year, `DOI ${node.doi}`].filter(Boolean).join(" · ") }),
      links.length ? element("div", { className: "publication-network-detail-links" }, links) : element("p", { className: "publication-network-detail-muted", text: "No external publication link is available." }),
    ]);

    const abstractChildren = [];
    if (node.abstract?.status === "available" && node.abstract.text) {
      abstractChildren.push(element("p", { text: node.abstract.text }));
      abstractChildren.push(element("small", { text: [node.abstract.source, node.abstract.license, node.abstract.caveat].filter(Boolean).join(" · ") }));
    } else {
      abstractChildren.push(element("p", { className: "publication-network-detail-muted", text: node.abstract?.caveat || "Abstract unavailable in this public snapshot." }));
    }

    const classification = makeSection("Evidence and availability", [
      element("p", { text: publicationInclusionBasis(node) }),
      element("dl", { className: "publication-network-readiness" }, [
        ["Inventory registry", review.inventoryAudit ? (review.inventoryAudit.registered ? "Registered" : "Not registered") : "Unavailable in this snapshot"],
        ["Methods inventory / access audit", inventoryEvidenceLabel(review.inventoryAudit?.evidenceStatus)],
        ["Contract review coverage", review.inventoryAudit ? `${review.inventoryAudit.rowsWithElevenSourceDispositions} of ${review.inventoryAudit.studyRowCount} rows have eleven explicit source dispositions` : "Unavailable in this snapshot"],
        ["Publication evidence", evidenceSummary(review.parameterStatusCounts)],
        ["Template availability", toolkitStatusLabel(node)],
        ["Native qualification", titleCase(review.nativeQualification)],
      ].map(([label, value]) => element("div", {}, [element("dt", { text: label }), element("dd", { text: value, attributes: { "data-pretext": true } })]))),
      element("p", { className: "publication-network-detail-muted", text: "Registry presence does not establish a complete Methods inventory. An audited contract can remain unresolved. A linked template supports preparation and preview; native acquisition qualification is a separate check." }),
    ]);
    const parameterChildren = review.studyIds.length
      ? review.studyIds.map(id => studyRecord(studyById.get(id)))
      : [element("p", {
        className: "publication-network-detail-muted",
        text: "No study-level review is attached to this publication.",
      })];

    detailBody.replaceChildren(
      overview,
      classification,
      makeSection("Study-level parameter review", parameterChildren),
      makeSection("Abstract", abstractChildren),
      makeSection("Citation metrics", [makeMetricGrid(node), element("small", { text: "Displayed-network metrics determine this map's size and topology. Broader source counts are provided for context. Neither is a study-quality score." })]),
      makeSection(`Cited by included papers (${incoming[index].length})`, [citationList(incoming[index], "No incoming citation links from other included papers are present.")]),
      makeSection(`References to included papers (${outgoing[index].length})`, [citationList(outgoing[index], "No outgoing citation links to other included papers are present.")]),
    );
  }

  function selectNode(index, trigger = graph) {
    if (!Number.isInteger(index) || !nodes[index]) return;
    if (!state.visibleSet.has(index)) {
      controls.search.value = "";
      updateSearch({ syncLink: false });
    }
    state.selected = index;
    state.lastFocus = trigger;
    state.lastFocusNode = trigger.classList?.contains("publication-network-result-button") ? index : null;
    renderDetail(index);
    detail.hidden = false;
    workspace.classList.add("detail-open");
    renderResults();
    updateStatus();
    requestDraw();
    updateLink();
    requestAnimationFrame(() => {
      resizeGraph();
      detail.focus({ preventScroll: true });
    });
  }

  function closeDetail({ restoreFocus = true } = {}) {
    state.selected = null;
    detail.hidden = true;
    workspace.classList.remove("detail-open");
    detailBody.replaceChildren();
    renderResults();
    updateStatus();
    requestAnimationFrame(resizeGraph);
    updateLink();
    if (restoreFocus) {
      const resultTrigger = state.lastFocusNode === null
        ? null
        : resultList.querySelector(`[data-node-index="${state.lastFocusNode}"]`);
      const focusTarget = resultTrigger || (state.lastFocus?.isConnected ? state.lastFocus : graph);
      focusTarget.focus({ preventScroll: true });
    }
  }

  for (const input of controls.layout) input.addEventListener("change", updateLayout);
  controls.search.addEventListener("input", () => updateSearch());
  controls.resultsSort.addEventListener("change", renderResults);
  resultMore.addEventListener("click", () => {
    state.resultLimit += RESULT_PAGE_SIZE;
    renderResults();
  });
  detailClose.addEventListener("click", () => closeDetail());

  fullscreenButton.addEventListener("click", async () => {
    if (document.fullscreenElement === shell) await document.exitFullscreen();
    else if (shell.requestFullscreen) await shell.requestFullscreen();
  });
  document.addEventListener("fullscreenchange", () => {
    fullscreenButton.textContent = document.fullscreenElement === shell ? "Exit full screen" : "Full screen";
    fullscreenButton.setAttribute("aria-label", fullscreenButton.textContent);
    requestAnimationFrame(resizeGraph);
  });

  graph.addEventListener("pointermove", (event) => {
    const index = hitTest(event.clientX, event.clientY);
    if (state.hovered !== index) {
      state.hovered = index;
      setTooltip(index, event.clientX, event.clientY);
      requestDraw();
    } else if (index !== null) {
      setTooltip(index, event.clientX, event.clientY);
    }
  });
  graph.addEventListener("pointerleave", () => {
    state.hovered = null;
    tooltip.hidden = true;
    requestDraw();
  });
  graph.addEventListener("click", (event) => {
    const index = hitTest(event.clientX, event.clientY);
    if (index !== null) selectNode(index, graph);
  });
  graph.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !detail.hidden) {
      event.preventDefault();
      closeDetail();
      return;
    }
    const navigable = state.visible;
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key) || !navigable.length) return;
    event.preventDefault();
    if (event.key === "Enter") {
      selectNode(state.selected ?? sortResults(navigable)[0], graph);
      return;
    }
    const ordered = sortResults(navigable);
    const current = Math.max(0, ordered.indexOf(state.selected));
    const direction = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    const next = ordered[(current + direction + ordered.length) % ordered.length];
    state.selected = next;
    renderDetail(next);
    detail.hidden = false;
    workspace.classList.add("detail-open");
    renderResults();
    updateStatus();
    requestDraw();
    updateLink();
  });
  detail.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDetail();
    }
  });

  root.publicationNetworkAudit = () => {
    const geometry = graphGeometry();
    return {
      schema: data.schema,
      renderer: "inline-svg",
      theme: document.documentElement.dataset.theme || "light",
      graph: {
        width: geometry.width,
        height: geometry.height,
        plotWidth: geometry.plotWidth,
        plotHeight: geometry.plotHeight,
        nodeElementCount: nodeElements.size,
        edgeElementCount: edgeElements.length,
      },
      layout: state.layout,
      visibleCount: state.visible.length,
      drawnEdgeCount: edges.filter(([source, target]) => state.visibleSet.has(source) && state.visibleSet.has(target)).length,
      totalEdgeCount: edges.length,
      overlapCount: state.overlapCount,
      nodes: state.visible.map((index) => {
        const point = state.projected.get(index) || screenPoint(index, geometry);
        return {
          id: nodes[index].id,
          x: point.x,
          y: point.y,
          radius: radiusFor(index, geometry),
          hasTemplate: hasTemplate(nodes[index]),
          parameterStatusCounts: nodes[index].studyReview.parameterStatusCounts,
          nativeQualification: nodes[index].studyReview.nativeQualification,
          status: toolkitStatus(nodes[index]),
          inDegree: nodes[index].network?.inDegree || 0,
          outDegree: nodes[index].network?.outDegree || 0,
          pageRank: nodes[index].network?.pageRank || 0,
          prominence: nodes[index].network?.prominence || 0,
          isolated: Boolean(nodes[index].network?.isolated),
        };
      }),
    };
  };

  const resizeObserver = new ResizeObserver(resizeGraph);
  resizeObserver.observe(stage);
  resizeObserver.observe(shell.querySelector(".publication-network-summary-row"));
  resizeObserver.observe(shell.querySelector(".publication-network-search-row"));
  loading.hidden = true;
  root.dataset.publicationNetworkState = "ready";
  root.dataset.publicationNetworkNodes = String(nodes.length);
  root.dataset.publicationNetworkEdges = String(edges.length);
  root.dataset.publicationNetworkRecords = String(data.counts.toolkitRecordJoins);
  root.dataset.publicationNetworkStudies = String(reviews.counts.studies);
  root.dataset.publicationNetworkRenderer = "inline-svg";
  const inventoryNote = root.querySelector("#publication-network-inventory-note");
  if (inventoryNote) {
    inventoryNote.textContent = inventoryAuditSummary(reviews.inventoryAudit);
    inventoryNote.title = reviews.inventoryAudit?.interpretation || "";
  }
  updateLayout();
  updateSearch({ syncLink: false });
  const initialStudy = initialUrl.searchParams.get("study");
  const studyAliases = reviews.studyRowAliases?.[initialStudy] || [];
  const selectedStudyIds = studyById.has(initialStudy) ? [initialStudy] : studyAliases.filter(id => studyById.has(id));
  const initialSelection = initialUrl.searchParams.get("publication") || studyById.get(selectedStudyIds[0])?.networkNodeId;
  if (initialSelection) {
    const index = nodes.findIndex(node => node.id === initialSelection || node.doi === initialSelection);
    if (index >= 0) {
      selectNode(index);
      const studyDetails = [...detailBody.querySelectorAll("[data-study-id]")].find(item => item.dataset.studyId === selectedStudyIds[0]);
      if (studyDetails) studyDetails.open = true;
      if (studyAliases.length && studyDetails) detailBody.prepend(element("p", {
        className: "publication-network-detail-muted", attributes: { role: "status", "data-study-alias-notice": true },
        text: `This earlier study record was split into ${selectedStudyIds.length} reviewed records. The current records are shown below.`,
      }));
      else if (initialStudy && !studyDetails) detailBody.prepend(element("p", { attributes: { role: "status" },
        text: "The linked study record is unavailable in this publication. Its current reviews are shown below." }));
    } else status.textContent = `This publication link is not in the current snapshot. ${nodes.length} papers remain searchable.`;
  }
  resizeGraph();
  root.dispatchEvent(new CustomEvent("pps:publication-network-ready", {
    bubbles: true,
    detail: { nodes: nodes.length, edges: edges.length, records: data.counts.toolkitRecordJoins },
  }));
}
