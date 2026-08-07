const DATA_URL = new URL("./publication_network.v1.json", import.meta.url);
const RESULT_PAGE_SIZE = 40;

const COLORS = Object.freeze({
  audiotactile: "#a9570d",
  visuotactile: "#087887",
  both: "#6b4ca1",
  other: "#526273",
  context: "#737a73",
  provisional: "#76529a",
});

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

function modalityFlags(node) {
  const audio = Boolean(node.modality?.audiotactile?.verified);
  const visualVerified = Boolean(node.modality?.visuotactile?.verified);
  const visualCandidate = node.modality?.visuotactile?.status === "provisional_keyword_candidate";
  return { audio, visualVerified, visualCandidate };
}

function categoryFor(node, includeProvisional = true) {
  const { audio, visualVerified, visualCandidate } = modalityFlags(node);
  const visual = visualVerified || (includeProvisional && visualCandidate);
  if (audio && visual) return "both";
  if (audio) return "audiotactile";
  if (visualVerified) return "visuotactile";
  if (includeProvisional && visualCandidate) return "provisional";
  if (node.corpus?.tier === "foundational_context") return "context";
  return "other";
}

function isVisibleByCategory(node, controls) {
  const { audio, visualVerified, visualCandidate } = modalityFlags(node);
  if (audio && controls.audiotactile.checked) return true;
  if (visualVerified && controls.visuotactile.checked) return true;
  if (visualCandidate && controls.provisional.checked && controls.visuotactile.checked) return true;
  if (audio || visualVerified || visualCandidate) return false;
  if (node.corpus?.tier === "foundational_context") return controls.context.checked;
  return controls.other.checked;
}

function metricValue(node, metric) {
  if (metric === "pageRank") return Number(node.centrality?.pageRank || 0);
  if (metric === "betweennessApprox") return Number(node.centrality?.betweennessApprox || 0);
  if (metric === "externalMax") return Number(node.citations?.externalMax || 0);
  if (metric === "uniform") return 1;
  return Number(node.citations?.withinCorpusReceived || 0);
}

function nodeSearchText(node) {
  return [node.title, node.authors?.join(" "), node.doi, node.year, node.venue]
    .join(" ")
    .toLocaleLowerCase();
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

export async function initializePublicationNetwork(root) {
  if (!root || root.dataset.publicationNetworkState === "ready") return;

  const controls = {
    search: root.querySelector("#publication-network-search"),
    audiotactile: root.querySelector("#publication-filter-audiotactile"),
    visuotactile: root.querySelector("#publication-filter-visuotactile"),
    other: root.querySelector("#publication-filter-other"),
    context: root.querySelector("#publication-filter-context"),
    provisional: root.querySelector("#publication-filter-provisional"),
    layout: [...root.querySelectorAll('input[name="publication-network-layout"]')],
    sizeMetric: root.querySelector("#publication-network-size-metric"),
    edgeMode: root.querySelector("#publication-network-edge-mode"),
    resultsSort: root.querySelector("#publication-network-results-sort"),
  };
  const shell = root.querySelector(".publication-network-shell");
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
  if (!shell || !canvas || !stage || !context2d) throw new Error("Publication-network canvas is unavailable.");

  const response = await fetch(DATA_URL);
  if (!response.ok) throw new Error(`Publication-network data request failed (${response.status}).`);
  const data = await response.json();
  if (data.schema !== "pps-publication-citation-network.v1") {
    throw new Error(`Unsupported publication-network schema: ${data.schema || "missing"}`);
  }

  const nodes = data.nodes;
  const edges = data.edges;
  const idToIndex = new Map(nodes.map((node, index) => [node.id, index]));
  const incoming = Array.from({ length: nodes.length }, () => []);
  const outgoing = Array.from({ length: nodes.length }, () => []);
  for (const [source, target] of edges) {
    outgoing[source].push(target);
    incoming[target].push(source);
  }
  const searchText = nodes.map(nodeSearchText);
  const state = {
    layout: "structure",
    visible: [],
    visibleSet: new Set(),
    selected: null,
    hovered: null,
    view: { scale: 1, x: 0, y: 0 },
    pointer: null,
    moved: false,
    resultLimit: RESULT_PAGE_SIZE,
    lastFocus: canvas,
    lastFocusNode: null,
    redrawPending: false,
    metricMaximum: 1,
  };

  function positionFor(index) {
    return nodes[index].layouts[state.layout] || nodes[index].layouts.structure;
  }

  function canvasGeometry() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    return {
      width,
      height,
      paddingX: Math.min(70, width * 0.08),
      paddingY: Math.min(64, height * 0.09),
    };
  }

  function screenPoint(index, geometry) {
    const { width, height, paddingX, paddingY } = geometry;
    const position = positionFor(index);
    const point = {
      x: paddingX + position.x * Math.max(1, width - paddingX * 2),
      y: paddingY + position.y * Math.max(1, height - paddingY * 2),
    };
    return {
      x: width / 2 + (point.x - width / 2) * state.view.scale + state.view.x,
      y: height / 2 + (point.y - height / 2) * state.view.scale + state.view.y,
    };
  }

  function radiusFor(index) {
    const metric = controls.sizeMetric.value;
    if (metric === "uniform") return state.selected === index ? 7.5 : 5;
    const maximum = state.metricMaximum;
    const value = metricValue(nodes[index], metric);
    const normalized = maximum > 0 ? Math.log1p(value) / Math.log1p(maximum) : 0;
    const radius = 2.7 + normalized * 7.8;
    return state.selected === index ? radius + 2 : radius;
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

  function drawTimelineGuides(width, height) {
    if (state.layout !== "timeline") return;
    const minYear = data.layoutBounds?.timeline?.minYear || 1900;
    const maxYear = data.layoutBounds?.timeline?.maxYear || new Date().getFullYear();
    const start = Math.ceil(minYear / 20) * 20;
    context2d.save();
    context2d.font = "11px system-ui, sans-serif";
    context2d.textAlign = "center";
    context2d.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() || "#65716a";
    context2d.strokeStyle = "rgba(112, 126, 118, 0.18)";
    context2d.lineWidth = 1;
    for (let year = start; year <= maxYear; year += 20) {
      const normalized = 0.04 + ((year - minYear) / Math.max(1, maxYear - minYear)) * 0.92;
      const raw = {
        x: Math.min(70, width * 0.08) + normalized * Math.max(1, width - Math.min(70, width * 0.08) * 2),
        y: height - 22,
      };
      const x = width / 2 + (raw.x - width / 2) * state.view.scale + state.view.x;
      context2d.beginPath();
      context2d.moveTo(x, 20);
      context2d.lineTo(x, height - 36);
      context2d.stroke();
      context2d.fillText(String(year), x, height - 15);
    }
    context2d.restore();
  }

  function shouldDrawEdge(source, target) {
    if (!state.visibleSet.has(source) || !state.visibleSet.has(target)) return false;
    const mode = controls.edgeMode.value;
    if (mode === "none") return false;
    if (mode === "neighborhood") return state.selected !== null && (source === state.selected || target === state.selected);
    return true;
  }

  function draw() {
    const geometry = canvasGeometry();
    const { width, height } = geometry;
    const projected = new Map(state.visible.map((index) => [index, screenPoint(index, geometry)]));
    context2d.clearRect(0, 0, width, height);
    drawTimelineGuides(width, height);

    const edgeMode = controls.edgeMode.value;
    if (edgeMode !== "none") {
      context2d.save();
      context2d.lineWidth = edgeMode === "all" ? 0.75 : 0.65;
      for (const [source, target] of edges) {
        if (!shouldDrawEdge(source, target)) continue;
        const from = projected.get(source);
        const to = projected.get(target);
        const selectedEdge = state.selected === source || state.selected === target;
        context2d.strokeStyle = selectedEdge
          ? "rgba(169, 87, 13, 0.72)"
          : edgeMode === "all" ? "rgba(82, 98, 115, 0.15)" : "rgba(82, 98, 115, 0.07)";
        context2d.lineWidth = selectedEdge ? 1.35 : (edgeMode === "all" ? 0.7 : 0.55);
        context2d.beginPath();
        context2d.moveTo(from.x, from.y);
        context2d.lineTo(to.x, to.y);
        context2d.stroke();
      }
      context2d.restore();
    }

    const ordered = [...state.visible].sort((left, right) =>
      nodes[left].centrality.influence - nodes[right].centrality.influence);
    for (const index of ordered) {
      const point = projected.get(index);
      const radius = radiusFor(index);
      if (point.x + radius < 0 || point.y + radius < 0 || point.x - radius > width || point.y - radius > height) continue;
      const category = categoryFor(nodes[index], controls.provisional.checked);
      context2d.save();
      context2d.beginPath();
      context2d.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context2d.globalAlpha = category === "provisional" ? 0.72 : 0.9;
      context2d.fillStyle = COLORS[category];
      context2d.fill();
      context2d.globalAlpha = 1;
      context2d.strokeStyle = state.selected === index ? "#fffdf8" : (state.hovered === index ? "#1f2a25" : "rgba(31, 42, 37, 0.45)");
      context2d.lineWidth = state.selected === index ? 3 : (state.hovered === index ? 2 : 0.8);
      if (category === "provisional") context2d.setLineDash([3, 2]);
      context2d.stroke();
      context2d.restore();
    }

    const labelIndex = state.hovered ?? state.selected;
    if (labelIndex !== null && state.visibleSet.has(labelIndex)) {
      const point = projected.get(labelIndex);
      const radius = radiusFor(labelIndex);
      const label = nodes[labelIndex].title.length > 74 ? `${nodes[labelIndex].title.slice(0, 71)}…` : nodes[labelIndex].title;
      context2d.save();
      context2d.font = "600 12px system-ui, sans-serif";
      context2d.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--text").trim() || "#1f2a25";
      context2d.fillText(label, point.x + radius + 5, point.y - radius - 2);
      context2d.restore();
    }
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const geometry = {
      width: Math.max(1, rect.width),
      height: Math.max(1, rect.height),
      paddingX: Math.min(70, Math.max(1, rect.width) * 0.08),
      paddingY: Math.min(64, Math.max(1, rect.height) * 0.09),
    };
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let best = null;
    let bestDistance = Infinity;
    for (const index of state.visible) {
      const point = screenPoint(index, geometry);
      const distance = Math.hypot(point.x - x, point.y - y);
      if (distance <= Math.max(9, radiusFor(index) + 4) && distance < bestDistance) {
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
      element("span", { text: `${node.citations.withinCorpusReceived} within-corpus citations · ${titleCase(categoryFor(node, controls.provisional.checked))}` }),
    );
    const stageRect = stage.getBoundingClientRect();
    tooltip.style.left = `${Math.max(12, Math.min(stageRect.width - 312, clientX - stageRect.left + 14))}px`;
    tooltip.style.top = `${Math.max(12, Math.min(stageRect.height - 130, clientY - stageRect.top + 14))}px`;
    tooltip.hidden = false;
  }

  function currentLayout() {
    return controls.layout.find((input) => input.checked)?.value || "structure";
  }

  function sortResults(indices) {
    const metric = controls.resultsSort.value;
    return [...indices].sort((left, right) => {
      if (metric === "year-desc") return (nodes[right].year || 0) - (nodes[left].year || 0) || nodes[left].title.localeCompare(nodes[right].title);
      if (metric === "year-asc") return (nodes[left].year || 9999) - (nodes[right].year || 9999) || nodes[left].title.localeCompare(nodes[right].title);
      if (metric === "title") return nodes[left].title.localeCompare(nodes[right].title);
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
        element("span", { text: `${node.year || "n.d."} · ${node.authors?.join(", ") || "Authors unavailable"} · ${node.citations.withinCorpusReceived} corpus citations` }),
      ]);
      button.addEventListener("click", () => selectNode(index, button));
      return element("li", {}, button);
    }));
    resultCount.textContent = `${sorted.length.toLocaleString()} result${sorted.length === 1 ? "" : "s"}`;
    resultMore.hidden = shown.length >= sorted.length;
  }

  function updateStatus() {
    let availableEdges = 0;
    let shownEdges = 0;
    for (const [source, target] of edges) {
      if (!state.visibleSet.has(source) || !state.visibleSet.has(target)) continue;
      availableEdges += 1;
      if (shouldDrawEdge(source, target)) shownEdges += 1;
    }
    const layoutLabel = state.layout === "timeline" ? "publication year" : "citation structure";
    status.textContent = `${state.visible.length.toLocaleString()} of ${nodes.length.toLocaleString()} publications · ${shownEdges.toLocaleString()} shown / ${availableEdges.toLocaleString()} available links · arranged by ${layoutLabel}`;
  }

  function updateVisible({ resetView = false } = {}) {
    const query = controls.search.value.trim().toLocaleLowerCase();
    state.layout = currentLayout();
    state.visible = nodes.map((_, index) => index).filter((index) =>
      isVisibleByCategory(nodes[index], controls) && (!query || searchText[index].includes(query)));
    state.visibleSet = new Set(state.visible);
    state.metricMaximum = Math.max(1, ...state.visible.map((index) => metricValue(nodes[index], controls.sizeMetric.value)));
    if (state.selected !== null && !state.visibleSet.has(state.selected)) closeDetail({ restoreFocus: false });
    state.resultLimit = RESULT_PAGE_SIZE;
    if (resetView) fitView();
    updateStatus();
    renderResults();
    requestDraw();
  }

  function fitView() {
    state.view = { scale: 1, x: 0, y: 0 };
    requestDraw();
  }

  function zoom(factor, clientX = null, clientY = null) {
    const { width, height } = canvasGeometry();
    const anchorX = clientX ?? width / 2;
    const anchorY = clientY ?? height / 2;
    const oldScale = state.view.scale;
    const nextScale = Math.max(0.5, Math.min(9, oldScale * factor));
    if (nextScale === oldScale) return;
    state.view.x = anchorX - width / 2 - ((anchorX - width / 2 - state.view.x) / oldScale) * nextScale;
    state.view.y = anchorY - height / 2 - ((anchorY - height / 2 - state.view.y) / oldScale) * nextScale;
    state.view.scale = nextScale;
    requestDraw();
  }

  function makeMetricGrid(node) {
    const descriptions = [
      ["Corpus citations", node.citations.withinCorpusReceived, "Incoming citation links from this snapshot"],
      ["Corpus references", node.citations.withinCorpusReferences, "Outgoing citation links in this snapshot"],
      ["External citations", node.citations.externalMax, "Largest provider count at snapshot time"],
      ["PageRank", compactNumber(node.centrality.pageRank, 6), "Directed within-corpus PageRank"],
      ["Betweenness", compactNumber(node.centrality.betweennessApprox, 6), "Approximate corpus-local betweenness"],
      ["Influence", compactNumber(node.centrality.influence, 4), "Navigation score; not a quality rating"],
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
      .filter((index) => state.visibleSet.has(index))
      .sort((left, right) => nodes[right].citations.withinCorpusReceived - nodes[left].citations.withinCorpusReceived)
      .slice(0, 20);
    if (!sorted.length) {
      return element("p", {
        className: "publication-network-detail-muted",
        text: "Citation neighbours are hidden by the current publication filters.",
      });
    }
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
    const details = element("details", { className: "publication-network-parameter-segment" });
    details.append(element("summary", {}, [
      element("span", { text: header }),
      element("small", { text: record.recreatable ? "Representable now" : "Incomplete parameters" }),
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
    detailTitle.textContent = node.title;
    detailKicker.textContent = `${node.year || "Year unavailable"} · ${node.venue || "Venue unavailable"}`;
    const badges = [];
    const flags = modalityFlags(node);
    if (flags.audio) badges.push(makeBadge("Audiotactile · verified", "publication-network-badge-at"));
    if (flags.visualVerified) badges.push(makeBadge("Visuotactile · verified", "publication-network-badge-vt"));
    if (flags.visualCandidate) badges.push(makeBadge("Visuotactile candidate · unverified", "publication-network-badge-provisional"));
    badges.push(makeBadge(titleCase(node.corpus.tier)));
    if (node.metadata.retracted) badges.push(makeBadge("Retracted"));

    const links = [
      safeExternalLink("Open DOI", node.links.doi),
      safeExternalLink("Publication source", node.links.primary && node.links.primary !== node.links.doi ? node.links.primary : ""),
      safeExternalLink("Open-access copy", node.links.openAccess),
    ].filter(Boolean);
    const overview = makeSection("Publication", [
      element("p", { className: "publication-network-byline", text: node.authors?.join(", ") || "Authors unavailable" }),
      element("div", { className: "publication-network-badges" }, badges),
      element("p", { className: "publication-network-detail-muted", text: [node.venue, node.publicationDate || node.year, node.doi ? `DOI ${node.doi}` : "DOI unavailable"].filter(Boolean).join(" · ") }),
      links.length ? element("div", { className: "publication-network-detail-links" }, links) : element("p", { className: "publication-network-detail-muted", text: "No external publication link is available." }),
    ]);

    const abstractChildren = [];
    if (node.abstract.status === "available" && node.abstract.text) {
      abstractChildren.push(element("p", { text: node.abstract.text }));
      abstractChildren.push(element("small", { text: `${node.abstract.source} · ${node.abstract.license}. ${node.abstract.caveat}` }));
    } else {
      abstractChildren.push(element("p", { className: "publication-network-detail-muted", text: node.abstract.caveat || "Abstract unavailable in this public snapshot." }));
    }

    const modality = makeSection("Classification", [
      element("p", { text: node.modality.audiotactile.basis }),
      element("p", { text: node.modality.visuotactile.basis }),
      node.modality.visuotactile.terms?.length
        ? element("small", { text: `Candidate terms: ${node.modality.visuotactile.terms.join(", ")}` })
        : null,
    ]);

    const records = node.toolkit.records || [];
    const toolkit = makeSection("PPS Toolkit parameters", records.length
      ? records.map(toolkitRecord)
      : [element("p", { className: "publication-network-detail-muted", text: "This publication has not been joined to a toolkit parameter audit by DOI." })]);

    detailBody.replaceChildren(
      overview,
      makeSection("Abstract", abstractChildren),
      modality,
      makeSection("Citation metrics", [makeMetricGrid(node), element("small", { text: "All centrality values are specific to this dated corpus and are navigation aids, not study-quality scores." })]),
      makeSection(`Cited by within corpus (${incoming[index].length})`, [citationList(incoming[index], "No incoming citation links are present in this snapshot.")]),
      makeSection(`References within corpus (${outgoing[index].length})`, [citationList(outgoing[index], "No outgoing citation links are present in this snapshot.")]),
      toolkit,
    );
  }

  function selectNode(index, trigger = canvas) {
    if (!Number.isInteger(index) || !state.visibleSet.has(index)) return;
    state.selected = index;
    state.lastFocus = trigger;
    state.lastFocusNode = trigger.classList?.contains("publication-network-result-button") ? index : null;
    renderDetail(index);
    detail.hidden = false;
    stage.classList.add("detail-open");
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
    stage.classList.remove("detail-open");
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

  function applyPreset(name) {
    controls.search.value = "";
    controls.audiotactile.checked = name !== "visuotactile";
    controls.visuotactile.checked = name !== "audiotactile";
    controls.other.checked = name === "all";
    controls.context.checked = name === "all";
    controls.provisional.checked = name !== "audiotactile";
    updateVisible({ resetView: true });
  }

  for (const control of [controls.search, controls.audiotactile, controls.visuotactile, controls.other, controls.context, controls.provisional]) {
    control.addEventListener("input", () => updateVisible());
  }
  for (const input of controls.layout) input.addEventListener("change", () => updateVisible({ resetView: true }));
  controls.sizeMetric.addEventListener("change", () => {
    state.metricMaximum = Math.max(1, ...state.visible.map((index) => metricValue(nodes[index], controls.sizeMetric.value)));
    requestDraw();
  });
  controls.edgeMode.addEventListener("change", () => {
    updateStatus();
    requestDraw();
  });
  controls.resultsSort.addEventListener("change", renderResults);
  for (const button of root.querySelectorAll("[data-network-preset]")) {
    button.addEventListener("click", () => applyPreset(button.dataset.networkPreset));
  }

  resultMore.addEventListener("click", () => {
    state.resultLimit += RESULT_PAGE_SIZE;
    renderResults();
  });
  detailClose.addEventListener("click", () => closeDetail());
  root.querySelector("#publication-network-zoom-in").addEventListener("click", () => zoom(1.25));
  root.querySelector("#publication-network-zoom-out").addEventListener("click", () => zoom(0.8));
  root.querySelector("#publication-network-fit").addEventListener("click", fitView);

  fullscreenButton.addEventListener("click", async () => {
    if (document.fullscreenElement === shell) await document.exitFullscreen();
    else if (shell.requestFullscreen) await shell.requestFullscreen();
  });
  document.addEventListener("fullscreenchange", () => {
    fullscreenButton.textContent = document.fullscreenElement === shell ? "Exit full screen" : "Full screen";
    fullscreenButton.setAttribute("aria-label", fullscreenButton.textContent);
    requestAnimationFrame(resizeCanvas);
  });

  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    state.pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, viewX: state.view.x, viewY: state.view.y };
    state.moved = false;
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (event) => {
    if (state.pointer?.id === event.pointerId) {
      const dx = event.clientX - state.pointer.x;
      const dy = event.clientY - state.pointer.y;
      if (Math.hypot(dx, dy) > 3) state.moved = true;
      state.view.x = state.pointer.viewX + dx;
      state.view.y = state.pointer.viewY + dy;
      tooltip.hidden = true;
      requestDraw();
      return;
    }
    const index = hitTest(event.clientX, event.clientY);
    if (state.hovered !== index) {
      state.hovered = index;
      setTooltip(index, event.clientX, event.clientY);
      requestDraw();
    } else if (index !== null) {
      setTooltip(index, event.clientX, event.clientY);
    }
  });
  const endPointer = (event) => {
    if (state.pointer?.id !== event.pointerId) return;
    const moved = state.moved;
    state.pointer = null;
    canvas.classList.remove("dragging");
    if (!moved) {
      const index = hitTest(event.clientX, event.clientY);
      if (index !== null) selectNode(index, canvas);
    }
  };
  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);
  canvas.addEventListener("pointerleave", () => {
    state.hovered = null;
    tooltip.hidden = true;
    requestDraw();
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    zoom(event.deltaY < 0 ? 1.14 : 0.88, event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !detail.hidden) {
      event.preventDefault();
      closeDetail();
      return;
    }
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key) || !state.visible.length) return;
    event.preventDefault();
    if (event.key === "Enter") {
      selectNode(state.selected ?? state.visible[0], canvas);
      return;
    }
    const ordered = sortResults(state.visible);
    const current = Math.max(0, ordered.indexOf(state.selected));
    const direction = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    const next = ordered[(current + direction + ordered.length) % ordered.length];
    state.selected = next;
    renderDetail(next);
    detail.hidden = false;
    stage.classList.add("detail-open");
    renderResults();
    requestDraw();
  });
  detail.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDetail();
    }
  });

  const resizeObserver = new ResizeObserver(resizeCanvas);
  resizeObserver.observe(stage);
  loading.hidden = true;
  root.dataset.publicationNetworkState = "ready";
  root.dataset.publicationNetworkNodes = String(nodes.length);
  root.dataset.publicationNetworkEdges = String(edges.length);
  updateVisible({ resetView: true });
  resizeCanvas();
  root.dispatchEvent(new CustomEvent("pps:publication-network-ready", {
    bubbles: true,
    detail: { nodes: nodes.length, edges: edges.length },
  }));
}
