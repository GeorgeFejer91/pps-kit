const DATA_URL = new URL("./publication_network.v2.json", import.meta.url);
const RESULT_PAGE_SIZE = 40;
const NODE_RADIUS_MIN = 0.0095;
const NODE_RADIUS_MAX = 0.018;

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
  if (metric === "pageRank") return Number(node.centrality?.pageRank || 0);
  if (metric === "betweennessApprox") return Number(node.centrality?.betweennessApprox || 0);
  if (metric === "externalMax") return Number(node.citations?.externalMax || 0);
  if (metric === "uniform") return 1;
  return Number(node.citations?.withinCorpusReceived || 0);
}

function inScopeRecords(node) {
  return (node.toolkit?.records || []).filter((record) =>
    record.coverageCategory && record.coverageCategory !== "adjacent_out_of_scope");
}

function isRunnable(node) {
  return inScopeRecords(node).some((record) => record.recreatable);
}

function nodeSearchText(node) {
  return [
    node.title,
    node.authors?.join(" "),
    node.doi,
    node.year,
    node.venue,
    ...inScopeRecords(node).map((record) => record.taskFamily),
  ].join(" ").toLocaleLowerCase();
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
    search: root.querySelector("#publication-network-search"),
    layout: [...root.querySelectorAll('input[name="publication-network-layout"]')],
    sizeMetric: root.querySelector("#publication-network-size-metric"),
    edgeMode: root.querySelector("#publication-network-edge-mode"),
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
  if (data.schema !== "pps-publication-citation-network.v2") {
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
  const searchText = nodes.map(nodeSearchText);
  const state = {
    layout: "prominence",
    visible: [],
    visibleSet: new Set(),
    selected: null,
    hovered: null,
    resultLimit: RESULT_PAGE_SIZE,
    lastFocus: canvas,
    lastFocusNode: null,
    redrawPending: false,
    metricMaximum: 1,
    projected: new Map(),
    overlapCount: 0,
  };

  function positionFor(index) {
    return nodes[index].layouts[state.layout] || nodes[index].layouts.prominence;
  }

  function canvasGeometry() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    const padding = Math.max(24, Math.min(52, Math.min(width, height) * 0.075));
    const plotSide = Math.max(1, Math.min(width, height) - padding * 2);
    return {
      width,
      height,
      plotSide,
      originX: (width - plotSide) / 2,
      originY: (height - plotSide) / 2,
    };
  }

  function screenPoint(index, geometry) {
    const position = positionFor(index);
    return {
      x: geometry.originX + position.x * geometry.plotSide,
      y: geometry.originY + position.y * geometry.plotSide,
    };
  }

  function radiusFor(index, geometry) {
    if (controls.sizeMetric.value === "uniform") return geometry.plotSide * 0.0125;
    const value = metricValue(nodes[index], controls.sizeMetric.value);
    const normalized = state.metricMaximum > 0
      ? Math.log1p(value) / Math.log1p(state.metricMaximum)
      : 0;
    return geometry.plotSide * (NODE_RADIUS_MIN + (NODE_RADIUS_MAX - NODE_RADIUS_MIN) * Math.sqrt(normalized));
  }

  function overlapCount(projected, geometry) {
    let count = 0;
    for (let left = 0; left < state.visible.length; left += 1) {
      const leftIndex = state.visible[left];
      const leftPoint = projected.get(leftIndex);
      for (let right = left + 1; right < state.visible.length; right += 1) {
        const rightIndex = state.visible[right];
        const rightPoint = projected.get(rightIndex);
        const minimum = radiusFor(leftIndex, geometry) + radiusFor(rightIndex, geometry) + 2;
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

  function shouldDrawEdge(source, target) {
    if (!state.visibleSet.has(source) || !state.visibleSet.has(target)) return false;
    const mode = controls.edgeMode.value;
    if (mode === "none") return false;
    if (mode === "neighborhood") {
      return state.selected !== null && (source === state.selected || target === state.selected);
    }
    return true;
  }

  function drawTimelineLabels(projected, geometry) {
    if (state.layout !== "timeline") return;
    context2d.save();
    context2d.fillStyle = cssValue("--muted", "#65716a");
    context2d.font = `${geometry.plotSide < 420 ? 8 : 10}px system-ui, sans-serif`;
    context2d.textAlign = "center";
    for (const index of state.visible) {
      const point = projected.get(index);
      const radius = radiusFor(index, geometry);
      context2d.fillText(String(nodes[index].year || "n.d."), point.x, point.y + radius + (geometry.plotSide < 420 ? 9 : 12));
    }
    context2d.textAlign = "left";
    context2d.font = "600 10px system-ui, sans-serif";
    context2d.fillText("Oldest → newest", geometry.originX, Math.max(14, geometry.originY - 12));
    context2d.restore();
  }

  function draw() {
    const geometry = canvasGeometry();
    const { width, height } = geometry;
    const projected = new Map(state.visible.map((index) => [index, screenPoint(index, geometry)]));
    state.projected = projected;
    state.overlapCount = overlapCount(projected, geometry);
    root.dataset.publicationNetworkOverlaps = String(state.overlapCount);
    context2d.clearRect(0, 0, width, height);

    if (controls.edgeMode.value !== "none") {
      context2d.save();
      for (const [source, target] of edges) {
        if (!shouldDrawEdge(source, target)) continue;
        const from = projected.get(source);
        const to = projected.get(target);
        const selectedEdge = state.selected === source || state.selected === target;
        context2d.strokeStyle = selectedEdge
          ? cssValue("--network-edge-selected", "rgba(169, 87, 13, 0.72)")
          : cssValue("--network-edge", "rgba(82, 98, 115, 0.15)");
        context2d.lineWidth = selectedEdge ? 1.45 : 0.65;
        context2d.beginPath();
        context2d.moveTo(from.x, from.y);
        context2d.lineTo(to.x, to.y);
        context2d.stroke();
      }
      context2d.restore();
    }

    const ordered = [...state.visible].sort((left, right) =>
      metricValue(nodes[left], controls.sizeMetric.value) - metricValue(nodes[right], controls.sizeMetric.value));
    for (const index of ordered) {
      const point = projected.get(index);
      const radius = radiusFor(index, geometry);
      const runnable = isRunnable(nodes[index]);
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
      context2d.fillStyle = runnable
        ? cssValue("--network-runnable", "#a9570d")
        : cssValue("--network-supported", "#e6c39e");
      context2d.fill();
      context2d.strokeStyle = state.hovered === index
        ? cssValue("--text", "#1f2a25")
        : cssValue("--network-node-stroke", "rgba(82, 58, 34, 0.72)");
      context2d.lineWidth = state.hovered === index ? 2.2 : (runnable ? 1.1 : 1.6);
      context2d.stroke();
      context2d.restore();
    }
    drawTimelineLabels(projected, geometry);
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
        text: `${node.citations.withinCorpusReceived} PPS-corpus citations · ${isRunnable(node) ? "Runnable profile" : "Supported paradigm; parameters incomplete"}`,
      }),
    );
    const stageRect = stage.getBoundingClientRect();
    tooltip.style.left = `${Math.max(12, Math.min(stageRect.width - 312, clientX - stageRect.left + 14))}px`;
    tooltip.style.top = `${Math.max(12, Math.min(stageRect.height - 130, clientY - stageRect.top + 14))}px`;
    tooltip.hidden = false;
  }

  function currentLayout() {
    return controls.layout.find((input) => input.checked)?.value || "prominence";
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
        element("span", {
          text: `${node.year || "n.d."} · ${node.authors?.join(", ") || "Authors unavailable"} · ${node.citations.withinCorpusReceived} PPS-corpus citations · ${isRunnable(node) ? "runnable" : "parameters incomplete"}`,
        }),
      ]);
      button.addEventListener("click", () => selectNode(index, button));
      return element("li", {}, button);
    }));
    resultCount.textContent = `${sorted.length.toLocaleString()} paper${sorted.length === 1 ? "" : "s"}`;
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
    const prefix = state.visible.length === nodes.length
      ? `${nodes.length.toLocaleString()} experiment papers`
      : `${state.visible.length.toLocaleString()} of ${nodes.length.toLocaleString()} experiment papers`;
    const layoutLabel = state.layout === "timeline" ? "publication-year grid" : "citation prominence";
    status.textContent = `${prefix} · ${data.counts.toolkitRecordJoins.toLocaleString()} supported task records · ${data.counts.toolkitRunnableNodes.toLocaleString()} runnable · ${shownEdges.toLocaleString()} / ${availableEdges.toLocaleString()} links shown · ${layoutLabel}`;
  }

  function updateVisible() {
    const query = controls.search.value.trim().toLocaleLowerCase();
    state.layout = currentLayout();
    state.visible = nodes.map((_, index) => index).filter((index) => !query || searchText[index].includes(query));
    state.visibleSet = new Set(state.visible);
    state.metricMaximum = Math.max(Number.EPSILON, ...nodes.map((node) => metricValue(node, controls.sizeMetric.value)));
    if (state.selected !== null && !state.visibleSet.has(state.selected)) closeDetail({ restoreFocus: false });
    state.resultLimit = RESULT_PAGE_SIZE;
    updateStatus();
    renderResults();
    requestDraw();
  }

  function makeMetricGrid(node) {
    const descriptions = [
      ["PPS-corpus citations", node.citations.withinCorpusReceived, "Incoming links from the broad 1,712-publication source snapshot"],
      ["PPS-corpus references", node.citations.withinCorpusReferences, "Outgoing links in the broad source snapshot"],
      ["External citations", node.citations.externalMax, "Largest provider count at snapshot time"],
      ["PageRank", compactNumber(node.centrality.pageRank, 6), "Directed broad-corpus PageRank"],
      ["Betweenness", compactNumber(node.centrality.betweennessApprox, 6), "Approximate broad-corpus betweenness"],
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
      .slice(0, 24);
    if (!sorted.length) {
      return element("p", {
        className: "publication-network-detail-muted",
        text: "Citation neighbours are hidden by the current search.",
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
      element("small", { text: record.recreatable ? "Runnable profile" : "Parameters incomplete" }),
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
    const records = inScopeRecords(node);
    const runnable = isRunnable(node);
    detailTitle.textContent = node.title;
    detailKicker.textContent = `${node.year || "Year unavailable"} · ${node.venue || "Venue unavailable"}`;
    const badges = [
      makeBadge("Audio–tactile experiment", "publication-network-badge-at"),
      makeBadge(
        runnable ? "Runnable Toolkit profile" : "Supported paradigm · parameters incomplete",
        runnable ? "publication-network-badge-runnable" : "publication-network-badge-incomplete",
      ),
    ];
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

    const classification = makeSection("Why this paper is included", [
      element("p", { text: `An exact DOI match connects this experimental paper to ${records.length} in-scope PPS Toolkit literature-audit record${records.length === 1 ? "" : "s"}.` }),
      element("p", { text: runnable
        ? "At least one audited task has enough reported parameters for a runnable Toolkit profile."
        : "The task structure is supported, but one or more publication parameters required for a runnable profile remain unavailable." }),
    ]);

    detailBody.replaceChildren(
      overview,
      makeSection("Abstract", abstractChildren),
      classification,
      makeSection("Citation metrics", [makeMetricGrid(node), element("small", { text: "Centrality values come from the dated broad PPS source corpus and are navigation aids, not study-quality scores." })]),
      makeSection(`Cited by included papers (${incoming[index].length})`, [citationList(incoming[index], "No incoming citation links from other included papers are present.")]),
      makeSection(`References to included papers (${outgoing[index].length})`, [citationList(outgoing[index], "No outgoing citation links to other included papers are present.")]),
      makeSection("PPS Toolkit parameters", records.map(toolkitRecord)),
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

  controls.search.addEventListener("input", updateVisible);
  for (const input of controls.layout) input.addEventListener("change", updateVisible);
  controls.sizeMetric.addEventListener("change", updateVisible);
  controls.edgeMode.addEventListener("change", () => {
    updateStatus();
    requestDraw();
  });
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
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(event.key) || !state.visible.length) return;
    event.preventDefault();
    if (event.key === "Enter") {
      selectNode(state.selected ?? sortResults(state.visible)[0], canvas);
      return;
    }
    const ordered = sortResults(state.visible);
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
      canvas: { width: geometry.width, height: geometry.height, plotSide: geometry.plotSide },
      layout: state.layout,
      visibleCount: state.visible.length,
      overlapCount: state.overlapCount,
      nodes: state.visible.map((index) => {
        const point = state.projected.get(index) || screenPoint(index, geometry);
        return {
          id: nodes[index].id,
          x: point.x,
          y: point.y,
          radius: radiusFor(index, geometry),
          runnable: isRunnable(nodes[index]),
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
  updateVisible();
  resizeCanvas();
  root.dispatchEvent(new CustomEvent("pps:publication-network-ready", {
    bubbles: true,
    detail: { nodes: nodes.length, edges: edges.length, records: data.counts.toolkitRecordJoins },
  }));
}
