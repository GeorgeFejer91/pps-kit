const DATA_URL = new URL("./publication_network.v3.json", import.meta.url);
const RESULT_PAGE_SIZE = 40;

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
  const status = toolkitStatus(node);
  if (status === "runnable") return "Runnable Toolkit profile";
  if (status === "supported_incomplete") return "Supported paradigm; parameters incomplete";
  if (status === "adjacent_scope_conflict") return "Adjacent / scope conflict";
  return "Not yet assessed for Toolkit";
}

function reviewPriority(node) {
  const status = toolkitStatus(node);
  if (status === "not_assessed") return 4;
  if (status === "adjacent_scope_conflict") return 3;
  if (status === "supported_incomplete") return 2;
  return 1;
}

function isRunnable(node) {
  return toolkitStatus(node) === "runnable";
}

function makeBadge(text, className = "") {
  return element("span", { className: `publication-network-badge ${className}`.trim(), text });
}

function makeSection(title, children = []) {
  return element("section", { className: "publication-network-detail-section" }, [
    element("h4", { text: title }),
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

function cssValue(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export async function initializePublicationNetwork(root) {
  if (!root || root.dataset.publicationNetworkState === "ready") return;

  const controls = {
    layout: [...root.querySelectorAll('input[name="publication-network-layout"]')],
    resultsSort: root.querySelector("#publication-network-results-sort"),
  };
  const shell = root.querySelector(".publication-network-shell");
  const workspace = root.querySelector("#publication-network-workspace");
  const canvas = root.querySelector("#publication-network-canvas");
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
  const context2d = canvas?.getContext("2d");
  if (!shell || !workspace || !canvas || !stage || !context2d) {
    throw new Error("Publication-network canvas is unavailable.");
  }

  const response = await fetch(DATA_URL);
  if (!response.ok) throw new Error(`Publication-network data request failed (${response.status}).`);
  const data = await response.json();
  if (data.schema !== "pps-publication-citation-network.v3") {
    throw new Error(`Unsupported publication-network schema: ${data.schema || "missing"}`);
  }

  const nodes = data.nodes;
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
    lastFocus: canvas,
    lastFocusNode: null,
    redrawPending: false,
    projected: new Map(),
    overlapCount: 0,
  };

  function positionFor(index) {
    return nodes[index].layouts[state.layout] || nodes[index].layouts.topology;
  }

  function canvasGeometry() {
    const rect = canvas.getBoundingClientRect();
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
      draw();
    });
  }

  function resizeCanvas() {
    const { width, height } = canvasGeometry();
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const pixelWidth = Math.round(width * ratio);
    const pixelHeight = Math.round(height * ratio);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    context2d.setTransform(ratio, 0, 0, ratio, 0, 0);
    requestDraw();
  }

  function drawTimelineLabels(projected, geometry) {
    if (state.layout !== "timeline") return;
    const years = [...new Set(state.visible.map((index) => nodes[index].year).filter(Number.isFinite))].sort((a, b) => a - b);
    if (!years.length) return;
    const guideYears = years.length <= 5
      ? years
      : [0, 0.25, 0.5, 0.75, 1].map((fraction) => years[Math.round((years.length - 1) * fraction)]);
    context2d.save();
    context2d.fillStyle = cssValue("--muted", "#65716a");
    context2d.font = `${geometry.plotScale < 420 ? 8 : 10}px system-ui, sans-serif`;
    context2d.textAlign = "center";
    context2d.strokeStyle = cssValue("--network-edge", "rgba(82, 98, 115, 0.15)");
    context2d.lineWidth = 0.75;
    for (const year of new Set(guideYears)) {
      const matches = state.visible.filter((index) => nodes[index].year === year);
      const x = matches.reduce((sum, index) => sum + projected.get(index).x, 0) / matches.length;
      context2d.beginPath();
      context2d.moveTo(x, geometry.originY);
      context2d.lineTo(x, geometry.originY + geometry.plotHeight);
      context2d.stroke();
      context2d.fillText(String(year), x, Math.max(12, geometry.originY - 10));
    }
    context2d.restore();
  }

  function selectedEdgeRelation(source, target) {
    if (state.selected === target) return "incoming";
    if (state.selected === source) return "outgoing";
    return "";
  }

  function drawCitationEdge(source, target, projected, geometry) {
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
    context2d.strokeStyle = relation === "incoming"
      ? cssValue("--network-edge-incoming", "rgba(35, 107, 148, 0.9)")
      : relation === "outgoing"
        ? cssValue("--network-edge-outgoing", "rgba(169, 87, 13, 0.9)")
        : cssValue("--network-edge", "rgba(82, 98, 115, 0.18)");
    context2d.fillStyle = context2d.strokeStyle;
    context2d.lineWidth = relation ? 1.7 : 0.65;
    context2d.beginPath();
    context2d.moveTo(startX, startY);
    context2d.lineTo(endX, endY);
    context2d.stroke();
    if (!relation) return;
    const arrowSize = 4.5;
    context2d.beginPath();
    context2d.moveTo(endX, endY);
    context2d.lineTo(endX - ux * arrowSize - uy * arrowSize * 0.58, endY - uy * arrowSize + ux * arrowSize * 0.58);
    context2d.lineTo(endX - ux * arrowSize + uy * arrowSize * 0.58, endY - uy * arrowSize - ux * arrowSize * 0.58);
    context2d.closePath();
    context2d.fill();
  }

  function draw() {
    const geometry = canvasGeometry();
    const { width, height } = geometry;
    const projected = new Map(state.visible.map((index) => [index, screenPoint(index, geometry)]));
    state.projected = projected;
    state.overlapCount = overlapCount(projected, geometry);
    root.dataset.publicationNetworkOverlaps = String(state.overlapCount);
    context2d.clearRect(0, 0, width, height);
    drawTimelineLabels(projected, geometry);

    context2d.save();
    const drawableEdges = [...edges]
      .sort(([leftSource, leftTarget], [rightSource, rightTarget]) =>
        Number(Boolean(selectedEdgeRelation(leftSource, leftTarget))) - Number(Boolean(selectedEdgeRelation(rightSource, rightTarget))));
    for (const [source, target] of drawableEdges) {
      drawCitationEdge(source, target, projected, geometry);
    }
    context2d.restore();

    const ordered = [...state.visible].sort((left, right) =>
      radiusFor(left, geometry) - radiusFor(right, geometry));
    for (const index of ordered) {
      const point = projected.get(index);
      const radius = radiusFor(index, geometry);
      const implemented = isRunnable(nodes[index]);
      context2d.save();
      if (state.selected === index) {
        context2d.beginPath();
        context2d.arc(point.x, point.y, radius + 4, 0, Math.PI * 2);
        context2d.strokeStyle = cssValue("--network-selection", "#246b55");
        context2d.lineWidth = 2.5;
        context2d.stroke();
      }
      context2d.beginPath();
      context2d.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context2d.fillStyle = implemented
        ? cssValue("--network-runnable", "#a9570d")
        : cssValue("--network-unassessed", "#f7f8f5");
      context2d.fill();
      context2d.strokeStyle = state.hovered === index
        ? cssValue("--text", "#1f2a25")
        : cssValue("--network-node-stroke", "rgba(82, 58, 34, 0.72)");
      context2d.lineWidth = state.hovered === index ? 2.2 : (implemented ? 1.1 : 1.6);
      context2d.setLineDash(implemented ? [] : [3, 2]);
      context2d.stroke();
      context2d.restore();
    }
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const geometry = canvasGeometry();
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
    const stageRect = stage.getBoundingClientRect();
    tooltip.style.left = `${Math.max(12, Math.min(stageRect.width - 312, clientX - stageRect.left + 14))}px`;
    tooltip.style.top = `${Math.max(12, Math.min(stageRect.height - 130, clientY - stageRect.top + 14))}px`;
    tooltip.hidden = false;
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
    const notImplemented = nodes.length - data.counts.toolkitRunnableNodes;
    const layoutLabel = state.layout === "timeline" ? "publication-year arrangement" : "citation topology";
    const selectedText = state.selected === null
      ? ""
      : ` · selected: ${nodes[state.selected].title} (${incoming[state.selected].length} incoming, ${outgoing[state.selected].length} outgoing)`;
    status.textContent = `${nodes.length.toLocaleString()} audio–tactile papers · ${data.counts.toolkitRunnableNodes} implemented · ${notImplemented} not yet · all ${edges.length.toLocaleString()} indexed direct citations shown · ${layoutLabel}${selectedText}`;
  }

  function updateLayout() {
    state.layout = currentLayout();
    state.resultLimit = RESULT_PAGE_SIZE;
    updateStatus();
    renderResults();
    requestDraw();
  }

  function makeMetricGrid(node) {
    const descriptions = [
      ["Citations in this map", node.network?.inDegree || 0, "Incoming links from the 97 displayed publications"],
      ["References in this map", node.network?.outDegree || 0, "Outgoing links to the 97 displayed publications"],
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
      .sort((left, right) => (nodes[right].network?.inDegree || 0) - (nodes[left].network?.inDegree || 0))
      .slice(0, 24);
    return element("ul", { className: "publication-network-citation-list" }, sorted.map((index) => {
      const button = element("button", {
        text: `${nodes[index].title} (${nodes[index].year || "n.d."})`,
        attributes: { type: "button" },
      });
      button.addEventListener("click", () => selectNode(index, button));
      return element("li", {}, button);
    }));
  }

  function toolkitRecord(record) {
    const header = record.citationShort || record.recordId || "Toolkit literature record";
    const adjacent = record.coverageCategory === "adjacent_out_of_scope";
    const details = element("details", { className: "publication-network-parameter-segment" });
    details.append(element("summary", {}, [
      element("span", { text: header }),
      element("small", { text: adjacent ? "Adjacent / out of scope" : record.recreatable ? "Runnable profile" : "Parameters incomplete" }),
    ]));
    const content = element("div", { className: "publication-network-detail-section" });
    if (record.taskFamily) content.append(element("p", { text: record.taskFamily }));
    if (record.templateIds?.length) content.append(element("small", { text: `Toolkit profiles: ${record.templateIds.join(", ")}` }));
    if (record.missingParameters?.length) content.append(element("small", { text: `Missing publication parameters: ${record.missingParameters.join(", ")}` }));
    const review = record.manualReview;
    if (!review) {
      content.append(element("p", { className: "publication-network-detail-muted", text: "No manual field-level parameter review is attached to this record." }));
    } else {
      content.append(element("small", { text: `Manual review: ${review.confidenceLabel || "confidence not labelled"}${review.confidenceScore ? ` (${compactNumber(review.confidenceScore, 2)})` : ""}` }));
      for (const [segmentName, fields] of Object.entries(review.segments || {})) {
        const segment = element("details", { className: "publication-network-parameter-segment" });
        const fieldEntries = Object.entries(fields || {});
        segment.append(element("summary", {}, [
          element("span", { text: titleCase(segmentName) }),
          element("small", { text: `${fieldEntries.length} fields` }),
        ]));
        segment.append(element("ul", { className: "publication-network-parameter-list" }, fieldEntries.map(([field, entry]) =>
          element("li", {}, [
            element("span", { className: "publication-network-parameter-field", text: titleCase(field) }),
            element("span", { text: entry.value === "" || entry.value === null ? "No reported value" : String(entry.value) }),
            element("span", { className: "publication-network-parameter-status", text: `${titleCase(entry.status)}${entry.pageOrSection ? ` · ${entry.pageOrSection}` : ""}` }),
            entry.evidenceNote ? element("small", { text: entry.evidenceNote }) : null,
          ]))));
        content.append(segment);
      }
    }
    details.append(content);
    return details;
  }

  function renderDetail(index) {
    const node = nodes[index];
    const records = node.toolkit?.records || [];
    const nodeStatus = toolkitStatus(node);
    const role = titleCase(node.corpus?.documentRole || "unclassified publication");
    const provenance = node.scope?.provenance || "legacy_confirmed";
    detailTitle.textContent = node.title;
    detailKicker.textContent = `${node.year || "Year unavailable"} · ${node.venue || "Venue unavailable"}`;
    const badges = [
      makeBadge("Audio–tactile publication", "publication-network-badge-at"),
      makeBadge(
        toolkitStatusLabel(node),
        nodeStatus === "runnable"
          ? "publication-network-badge-runnable"
          : nodeStatus === "supported_incomplete"
            ? "publication-network-badge-incomplete"
            : nodeStatus === "adjacent_scope_conflict"
              ? "publication-network-badge-conflict"
              : "publication-network-badge-unassessed",
      ),
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

    const inclusionBasis = provenance === "later_exact_doi_audit"
      ? "This publication was added through a later exact-DOI literature-audit match identifying an in-scope audio–tactile PPS task."
      : "This publication belongs to the manually verified legacy audio–tactile PPS citation set.";
    const statusExplanation = nodeStatus === "runnable"
      ? `An exact DOI match links ${records.length} Toolkit literature-audit record${records.length === 1 ? "" : "s"}; at least one task has enough reported parameters for a runnable profile.`
      : nodeStatus === "supported_incomplete"
        ? `An exact DOI match links ${records.length} in-scope Toolkit literature-audit record${records.length === 1 ? "" : "s"}. The paradigm is supported, but publication parameters needed for a runnable profile remain unavailable.`
        : nodeStatus === "adjacent_scope_conflict"
          ? "The citation audit classifies this publication as audio–tactile, while the Toolkit literature audit currently marks its matched task as adjacent or out of scope. It needs an explicit scope decision."
          : "No exact-DOI Toolkit literature-audit record is linked yet. The publication remains visible so its paradigm can be assessed instead of being silently excluded.";
    const classification = makeSection("Toolkit inclusion status", [
      element("p", { text: inclusionBasis }),
      element("p", { text: statusExplanation }),
    ]);

    const parameterChildren = records.length
      ? records.map(toolkitRecord)
      : [element("p", {
        className: "publication-network-detail-muted",
        text: "Not yet assessed: no exact-DOI Toolkit parameter record is attached to this publication.",
      })];

    detailBody.replaceChildren(
      overview,
      makeSection("Abstract", abstractChildren),
      classification,
      makeSection("Citation metrics", [makeMetricGrid(node), element("small", { text: "Displayed-network metrics determine this map's size and topology. Broader source counts are provided for context. Neither is a study-quality score." })]),
      makeSection(`Cited by included papers (${incoming[index].length})`, [citationList(incoming[index], "No incoming citation links from other included papers are present.")]),
      makeSection(`References to included papers (${outgoing[index].length})`, [citationList(outgoing[index], "No outgoing citation links to other included papers are present.")]),
      makeSection("PPS Toolkit parameters", parameterChildren),
    );
  }

  function selectNode(index, trigger = canvas) {
    if (!Number.isInteger(index) || !state.visibleSet.has(index)) return;
    state.selected = index;
    state.lastFocus = trigger;
    state.lastFocusNode = trigger.classList?.contains("publication-network-result-button") ? index : null;
    renderDetail(index);
    detail.hidden = false;
    workspace.classList.add("detail-open");
    renderResults();
    updateStatus();
    requestDraw();
    requestAnimationFrame(() => {
      resizeCanvas();
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
    requestAnimationFrame(resizeCanvas);
    if (restoreFocus) {
      const resultTrigger = state.lastFocusNode === null
        ? null
        : resultList.querySelector(`[data-node-index="${state.lastFocusNode}"]`);
      const focusTarget = resultTrigger || (state.lastFocus?.isConnected ? state.lastFocus : canvas);
      focusTarget.focus({ preventScroll: true });
    }
  }

  for (const input of controls.layout) input.addEventListener("change", updateLayout);
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
    requestAnimationFrame(resizeCanvas);
  });

  canvas.addEventListener("pointermove", (event) => {
    const index = hitTest(event.clientX, event.clientY);
    if (state.hovered !== index) {
      state.hovered = index;
      setTooltip(index, event.clientX, event.clientY);
      requestDraw();
    } else if (index !== null) {
      setTooltip(index, event.clientX, event.clientY);
    }
  });
  canvas.addEventListener("pointerleave", () => {
    state.hovered = null;
    tooltip.hidden = true;
    requestDraw();
  });
  canvas.addEventListener("click", (event) => {
    const index = hitTest(event.clientX, event.clientY);
    if (index !== null) selectNode(index, canvas);
  });
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !detail.hidden) {
      event.preventDefault();
      closeDetail();
      return;
    }
    const navigable = state.visible;
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key) || !navigable.length) return;
    event.preventDefault();
    if (event.key === "Enter") {
      selectNode(state.selected ?? sortResults(navigable)[0], canvas);
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
  });
  detail.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDetail();
    }
  });

  root.publicationNetworkAudit = () => {
    const geometry = canvasGeometry();
    return {
      schema: data.schema,
      canvas: {
        width: geometry.width,
        height: geometry.height,
        plotWidth: geometry.plotWidth,
        plotHeight: geometry.plotHeight,
      },
      layout: state.layout,
      visibleCount: state.visible.length,
      drawnEdgeCount: edges.length,
      totalEdgeCount: edges.length,
      overlapCount: state.overlapCount,
      nodes: state.visible.map((index) => {
        const point = state.projected.get(index) || screenPoint(index, geometry);
        return {
          id: nodes[index].id,
          x: point.x,
          y: point.y,
          radius: radiusFor(index, geometry),
          implemented: isRunnable(nodes[index]),
          runnable: isRunnable(nodes[index]),
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

  const resizeObserver = new ResizeObserver(resizeCanvas);
  resizeObserver.observe(stage);
  loading.hidden = true;
  root.dataset.publicationNetworkState = "ready";
  root.dataset.publicationNetworkNodes = String(nodes.length);
  root.dataset.publicationNetworkEdges = String(edges.length);
  root.dataset.publicationNetworkRecords = String(data.counts.toolkitRecordJoins);
  updateLayout();
  resizeCanvas();
  root.dispatchEvent(new CustomEvent("pps:publication-network-ready", {
    bubbles: true,
    detail: { nodes: nodes.length, edges: edges.length, records: data.counts.toolkitRecordJoins },
  }));
}
