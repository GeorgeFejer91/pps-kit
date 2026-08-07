const DATA_URL = new URL("./publication_network.v1.json", import.meta.url);
const RESULT_PAGE_SIZE = 20;
const LANDMARK_LIMIT = 10;

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

function isVerifiedAudiotactile(node) {
  return Boolean(node.modality?.audiotactile?.verified);
}

function nodeSearchText(node) {
  return [node.title, node.authors?.join(" "), node.doi, node.year, node.venue]
    .join(" ")
    .toLocaleLowerCase();
}

function authorYear(node) {
  const firstAuthor = String(node.authors?.[0] || "Author unavailable").trim();
  const surname = firstAuthor.split(/\s+/).at(-1)?.replace(/[,.]+$/g, "") || firstAuthor;
  const author = (node.authors?.length || 0) > 1 ? `${surname} et al.` : surname;
  return `${author}${node.year ? `, ${node.year}` : ""}`;
}

function paperKind(node) {
  const role = String(node.corpus?.documentRole || "").toLocaleLowerCase();
  if (role.includes("review") || role.includes("meta_analysis") || role.includes("theory")) return "Review or synthesis";
  if (role.includes("method")) return "Methods paper";
  if (role.includes("model") && !role.includes("empirical")) return "Model paper";
  return "Empirical paper";
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
    layout: [...root.querySelectorAll('input[name="publication-network-layout"]')],
    resultsSort: root.querySelector("#publication-network-results-sort"),
  };
  const shell = root.querySelector(".publication-network-shell");
  const canvas = root.querySelector("#publication-network-canvas");
  const stage = root.querySelector("#publication-network-stage");
  const mapPane = root.querySelector(".publication-network-map-pane");
  const loading = root.querySelector("#publication-network-loading");
  const tooltip = root.querySelector("#publication-network-tooltip");
  const status = root.querySelector("#publication-network-status");
  const resultPanel = root.querySelector("#publication-network-results-panel");
  const resultCount = root.querySelector("#publication-network-results-count");
  const resultList = root.querySelector("#publication-network-results");
  const resultMore = root.querySelector("#publication-network-results-more");
  const detail = root.querySelector("#publication-network-detail");
  const detailTitle = root.querySelector("#publication-network-detail-title");
  const detailKicker = root.querySelector("#publication-network-detail-kicker");
  const detailBody = root.querySelector("#publication-network-detail-body");
  const detailClose = root.querySelector("#publication-network-detail-close");
  const fullscreenButton = root.querySelector("#publication-network-fullscreen");
  const resetButton = root.querySelector("#publication-network-reset");
  const context2d = canvas?.getContext("2d");
  if (!shell || !canvas || !stage || !mapPane || !context2d || !resultPanel) {
    throw new Error("Audiotactile publication-map canvas is unavailable.");
  }

  const response = await fetch(DATA_URL);
  if (!response.ok) throw new Error(`Publication-network data request failed (${response.status}).`);
  const data = await response.json();
  if (data.schema !== "pps-publication-citation-network.v1") {
    throw new Error(`Unsupported publication-network schema: ${data.schema || "missing"}`);
  }

  const nodes = data.nodes;
  const edges = data.edges;
  const verifiedAudiotactile = nodes
    .map((node, index) => isVerifiedAudiotactile(node) ? index : null)
    .filter(Number.isInteger);
  const verifiedAudiotactileSet = new Set(verifiedAudiotactile);
  const audiotactileEdges = edges.filter(([source, target]) =>
    verifiedAudiotactileSet.has(source) && verifiedAudiotactileSet.has(target));
  const audiotactileIncoming = Array.from({ length: nodes.length }, () => []);
  const audiotactileOutgoing = Array.from({ length: nodes.length }, () => []);
  for (const [source, target] of audiotactileEdges) {
    audiotactileOutgoing[source].push(target);
    audiotactileIncoming[target].push(source);
  }
  const audiotactileReceived = new Uint16Array(nodes.length);
  const audiotactileReferences = new Uint16Array(nodes.length);
  for (const index of verifiedAudiotactile) {
    audiotactileReceived[index] = audiotactileIncoming[index].length;
    audiotactileReferences[index] = audiotactileOutgoing[index].length;
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
    const layouts = nodes[index].layouts || {};
    if (state.layout === "timeline") return layouts.audiotactileTimeline || layouts.timeline;
    return layouts.audiotactileStructure || layouts.structure;
  }

  function canvasGeometry() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    return {
      width,
      height,
      paddingX: Math.min(64, width * 0.075),
      paddingY: Math.min(56, height * 0.085),
    };
  }

  function basePoint(index, geometry) {
    const { width, height, paddingX, paddingY } = geometry;
    const position = positionFor(index);
    return {
      x: paddingX + position.x * Math.max(1, width - paddingX * 2),
      y: paddingY + position.y * Math.max(1, height - paddingY * 2),
    };
  }

  function screenPoint(index, geometry) {
    const { width, height } = geometry;
    const point = basePoint(index, geometry);
    return {
      x: width / 2 + (point.x - width / 2) * state.view.scale + state.view.x,
      y: height / 2 + (point.y - height / 2) * state.view.scale + state.view.y,
    };
  }

  function radiusFor(index) {
    const maximum = state.metricMaximum;
    const value = audiotactileReceived[index];
    const normalized = maximum > 0 ? Math.log1p(value) / Math.log1p(maximum) : 0;
    const radius = 4.2 + normalized * 6.8;
    return state.selected === index ? radius + 2.2 : radius;
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

  function cssColor(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function drawTimelineGuides(geometry) {
    if (state.layout !== "timeline") return;
    const bounds = data.layoutBounds?.audiotactileTimeline || data.layoutBounds?.timeline || {};
    const minYear = bounds.minYear || 2000;
    const maxYear = bounds.maxYear || new Date().getFullYear();
    const start = Math.ceil(minYear / 5) * 5;
    context2d.save();
    context2d.font = "11px system-ui, sans-serif";
    context2d.textAlign = "center";
    context2d.fillStyle = cssColor("--muted", "#65716a");
    context2d.strokeStyle = cssColor("--line", "#d9dfd6");
    context2d.globalAlpha = 0.7;
    for (let year = start; year <= maxYear; year += 5) {
      const normalized = 0.04 + ((year - minYear) / Math.max(1, maxYear - minYear)) * 0.92;
      const rawX = geometry.paddingX + normalized * Math.max(1, geometry.width - geometry.paddingX * 2);
      const x = geometry.width / 2 + (rawX - geometry.width / 2) * state.view.scale + state.view.x;
      context2d.beginPath();
      context2d.moveTo(x, 20);
      context2d.lineTo(x, geometry.height - 44);
      context2d.stroke();
      context2d.fillText(String(year), x, geometry.height - 20);
    }
    context2d.restore();
  }

  function drawDirectedEdge(source, target, projected, color, alpha) {
    const from = projected.get(source);
    const to = projected.get(target);
    if (!from || !to) return;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const ux = dx / distance;
    const uy = dy / distance;
    const start = {
      x: from.x + ux * (radiusFor(source) + 2),
      y: from.y + uy * (radiusFor(source) + 2),
    };
    const end = {
      x: to.x - ux * (radiusFor(target) + 3),
      y: to.y - uy * (radiusFor(target) + 3),
    };
    context2d.save();
    context2d.strokeStyle = color;
    context2d.fillStyle = color;
    context2d.globalAlpha = alpha;
    context2d.lineWidth = 1.6;
    context2d.beginPath();
    context2d.moveTo(start.x, start.y);
    context2d.lineTo(end.x, end.y);
    context2d.stroke();
    const arrowLength = 6;
    const arrowWidth = 3.5;
    context2d.beginPath();
    context2d.moveTo(end.x, end.y);
    context2d.lineTo(end.x - ux * arrowLength - uy * arrowWidth, end.y - uy * arrowLength + ux * arrowWidth);
    context2d.lineTo(end.x - ux * arrowLength + uy * arrowWidth, end.y - uy * arrowLength - ux * arrowWidth);
    context2d.closePath();
    context2d.fill();
    context2d.restore();
  }

  function overlaps(box, boxes) {
    return boxes.some((other) =>
      box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top);
  }

  function drawLandmarkLabels(geometry, projected) {
    if (!state.visible.length) return;
    const ranked = [...state.visible].sort((left, right) =>
      audiotactileReceived[right] - audiotactileReceived[left]
      || nodes[left].title.localeCompare(nodes[right].title));
    const occupied = [];
    context2d.save();
    context2d.font = `${geometry.width < 520 ? 10 : 11}px system-ui, sans-serif`;
    context2d.textBaseline = "middle";

    const paintLabel = (index, box, { selected = false, leader = false } = {}) => {
      const label = authorYear(nodes[index]);
      const point = projected.get(index);
      const boxWidth = box.right - box.left;
      const boxHeight = box.bottom - box.top;
      if (leader) {
        const targetX = point.x < geometry.width / 2 ? box.right : box.left;
        context2d.save();
        context2d.strokeStyle = cssColor("--line-strong", "#bcc7bd");
        context2d.globalAlpha = 0.72;
        context2d.lineWidth = 1;
        context2d.beginPath();
        context2d.moveTo(point.x, point.y);
        context2d.lineTo(targetX, box.top + boxHeight / 2);
        context2d.stroke();
        context2d.restore();
      }
      occupied.push(box);
      context2d.globalAlpha = selected ? 0.98 : 0.92;
      context2d.fillStyle = cssColor("--surface", "#ffffff");
      context2d.strokeStyle = selected
        ? cssColor("--primary", "#246b55")
        : cssColor("--line-strong", "#bcc7bd");
      context2d.lineWidth = selected ? 1.5 : 1;
      context2d.beginPath();
      context2d.roundRect(box.left, box.top, boxWidth, boxHeight, 5);
      context2d.fill();
      context2d.stroke();
      context2d.globalAlpha = 1;
      context2d.fillStyle = cssColor("--text", "#202621");
      context2d.fillText(label, box.left + 6, box.top + boxHeight / 2 + 0.5);
    };

    const emphasized = [state.selected, state.hovered]
      .filter((index, order, values) => Number.isInteger(index) && values.indexOf(index) === order);
    for (const index of emphasized) {
      if (!state.visibleSet.has(index)) continue;
      const label = authorYear(nodes[index]);
      const point = projected.get(index);
      const boxWidth = context2d.measureText(label).width + 12;
      const boxHeight = 22;
      const gap = radiusFor(index) + 7;
      const candidates = [
        { left: point.x + gap, top: point.y - boxHeight / 2 },
        { left: point.x - gap - boxWidth, top: point.y - boxHeight / 2 },
        { left: point.x - boxWidth / 2, top: point.y - gap - boxHeight },
        { left: point.x - boxWidth / 2, top: point.y + gap },
      ].map((box) => ({ ...box, right: box.left + boxWidth, bottom: box.top + boxHeight }));
      const box = candidates.find((candidate) =>
        candidate.left >= 5 && candidate.right <= geometry.width - 5
        && candidate.top >= 5 && candidate.bottom <= geometry.height - 52
        && !overlaps(candidate, occupied));
      if (box) paintLabel(index, box, { selected: index === state.selected });
    }

    const landmarkCount = geometry.width < 520 ? 0 : (geometry.width < 720 ? 6 : LANDMARK_LIMIT);
    const landmarks = ranked
      .filter((index) => !emphasized.includes(index))
      .slice(0, landmarkCount);
    if (geometry.width >= 600) {
      const byX = [...landmarks].sort((left, right) => projected.get(left).x - projected.get(right).x);
      const midpoint = Math.ceil(byX.length / 2);
      const sides = [
        { indices: byX.slice(0, midpoint), side: "left" },
        { indices: byX.slice(midpoint), side: "right" },
      ];
      for (const { indices, side } of sides) {
        indices.sort((left, right) => projected.get(left).y - projected.get(right).y);
        const top = 76;
        const bottom = geometry.height - 78;
        indices.forEach((index, order) => {
          const label = authorYear(nodes[index]);
          const boxWidth = context2d.measureText(label).width + 12;
          const boxHeight = 22;
          const centerY = top + ((order + 0.5) / Math.max(1, indices.length)) * (bottom - top);
          const left = side === "left" ? 12 : geometry.width - boxWidth - 12;
          const box = { left, top: centerY - boxHeight / 2, right: left + boxWidth, bottom: centerY + boxHeight / 2 };
          if (!overlaps(box, occupied)) paintLabel(index, box, { leader: true });
        });
      }
    } else {
      for (const index of landmarks) {
        const label = authorYear(nodes[index]);
        const point = projected.get(index);
        const boxWidth = context2d.measureText(label).width + 12;
        const boxHeight = 22;
        const gap = radiusFor(index) + 6;
        const candidates = [
          { left: point.x + gap, top: point.y - boxHeight / 2 },
          { left: point.x - gap - boxWidth, top: point.y - boxHeight / 2 },
          { left: point.x - boxWidth / 2, top: point.y - gap - boxHeight },
        ].map((box) => ({ ...box, right: box.left + boxWidth, bottom: box.top + boxHeight }));
        const box = candidates.find((candidate) =>
          candidate.left >= 5 && candidate.right <= geometry.width - 5
          && candidate.top >= 5 && candidate.bottom <= geometry.height - 52
          && !overlaps(candidate, occupied));
        if (box) paintLabel(index, box);
      }
    }
    context2d.restore();
  }

  function draw() {
    const geometry = canvasGeometry();
    const projected = new Map(state.visible.map((index) => [index, screenPoint(index, geometry)]));
    context2d.clearRect(0, 0, geometry.width, geometry.height);
    drawTimelineGuides(geometry);

    const active = state.selected ?? state.hovered;
    if (active !== null && state.visibleSet.has(active)) {
      const incomingColor = cssColor("--network-incoming", "#087887");
      const outgoingColor = cssColor("--network-outgoing", "#76529a");
      const alpha = state.selected === active ? 0.78 : 0.5;
      for (const [source, target] of audiotactileEdges) {
        if (!state.visibleSet.has(source) || !state.visibleSet.has(target)) continue;
        if (target === active) drawDirectedEdge(source, target, projected, incomingColor, alpha);
        else if (source === active) drawDirectedEdge(source, target, projected, outgoingColor, alpha);
      }
    }

    const ordered = [...state.visible].sort((left, right) =>
      audiotactileReceived[left] - audiotactileReceived[right]);
    for (const index of ordered) {
      const point = projected.get(index);
      const radius = radiusFor(index);
      if (point.x + radius < 0 || point.y + radius < 0
        || point.x - radius > geometry.width || point.y - radius > geometry.height) continue;
      context2d.save();
      context2d.beginPath();
      context2d.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context2d.fillStyle = state.selected === index
        ? cssColor("--primary", "#246b55")
        : cssColor("--network-at", "#a9570d");
      context2d.globalAlpha = state.hovered === index || state.selected === index ? 1 : 0.88;
      context2d.fill();
      context2d.globalAlpha = 1;
      context2d.strokeStyle = state.selected === index
        ? cssColor("--surface", "#ffffff")
        : cssColor("--line-strong", "#bcc7bd");
      context2d.lineWidth = state.selected === index ? 3 : (state.hovered === index ? 2.2 : 1);
      context2d.stroke();
      context2d.restore();
    }
    drawLandmarkLabels(geometry, projected);
  }

  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const geometry = canvasGeometry();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let best = null;
    let bestDistance = Infinity;
    for (const index of state.visible) {
      const point = screenPoint(index, geometry);
      const distance = Math.hypot(point.x - x, point.y - y);
      if (distance <= Math.max(12, radiusFor(index) + 7) && distance < bestDistance) {
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
      element("span", { text: `${authorYear(node)} · ${paperKind(node)}` }),
      element("span", { text: `${audiotactileReceived[index]} citations from papers in this verified map` }),
    );
    const paneRect = mapPane.getBoundingClientRect();
    tooltip.style.left = `${Math.max(12, Math.min(paneRect.width - 312, clientX - paneRect.left + 14))}px`;
    tooltip.style.top = `${Math.max(12, Math.min(paneRect.height - 130, clientY - paneRect.top + 14))}px`;
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
      return audiotactileReceived[right] - audiotactileReceived[left]
        || audiotactileReferences[right] - audiotactileReferences[left]
        || nodes[left].title.localeCompare(nodes[right].title);
    });
  }

  function renderResults() {
    const sorted = sortResults(state.visible);
    const shown = sorted.slice(0, state.resultLimit);
    resultList.replaceChildren(...shown.map((index) => {
      const node = nodes[index];
      const received = audiotactileReceived[index];
      const button = element("button", {
        className: "publication-network-result-button",
        attributes: {
          type: "button",
          "data-node-index": index,
          "aria-current": state.selected === index ? "true" : "false",
        },
      }, [
        element("strong", { text: node.title }),
        element("span", { text: `${authorYear(node)} · ${received} citation${received === 1 ? "" : "s"} in this map` }),
        element("small", { className: "publication-network-result-kind", text: paperKind(node) }),
      ]);
      button.addEventListener("click", () => {
        controls.search.value = "";
        updateVisible();
        selectNode(index, button);
      });
      return element("li", {}, button);
    }));
    const query = controls.search.value.trim();
    resultCount.textContent = `${sorted.length.toLocaleString()} ${query ? "matches" : "studies"}`;
    resultMore.hidden = shown.length >= sorted.length;
  }

  function updateStatus() {
    if (!state.visible.length) {
      status.textContent = "No verified audiotactile papers match this search.";
      return;
    }
    const visibleEdges = audiotactileEdges.filter(([source, target]) =>
      state.visibleSet.has(source) && state.visibleSet.has(target));
    if (state.selected !== null && state.visibleSet.has(state.selected)) {
      const received = audiotactileReceived[state.selected];
      status.textContent = `${authorYear(nodes[state.selected])} · cited by ${received} verified paper${received === 1 ? "" : "s"} · references ${audiotactileReferences[state.selected]}`;
      return;
    }
    status.textContent = `${state.visible.length.toLocaleString()} manually verified audiotactile PPS paper${state.visible.length === 1 ? "" : "s"} · ${visibleEdges.length.toLocaleString()} citation${visibleEdges.length === 1 ? "" : "s"} between them`;
  }

  function updateVisible({ resetView = false } = {}) {
    const query = controls.search.value.trim().toLocaleLowerCase();
    state.layout = currentLayout();
    state.visible = verifiedAudiotactile.filter((index) => !query || searchText[index].includes(query));
    state.visibleSet = new Set(state.visible);
    state.metricMaximum = Math.max(1, ...state.visible.map((index) => audiotactileReceived[index]));
    if (state.selected !== null && !state.visibleSet.has(state.selected)) closeDetail({ restoreFocus: false });
    state.resultLimit = query ? Math.max(RESULT_PAGE_SIZE, state.visible.length) : RESULT_PAGE_SIZE;
    updateStatus();
    renderResults();
    if (resetView) requestAnimationFrame(fitView);
    else requestDraw();
  }

  function fitView() {
    const geometry = canvasGeometry();
    if (!state.visible.length) {
      state.view.scale = 1;
      state.view.x = 0;
      state.view.y = 0;
      requestDraw();
      return;
    }
    const points = state.visible.map((index) => {
      const position = positionFor(index);
      return {
        x: geometry.paddingX + position.x * Math.max(1, geometry.width - geometry.paddingX * 2),
        y: geometry.paddingY + position.y * Math.max(1, geometry.height - geometry.paddingY * 2),
      };
    });
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y));
    const maxY = Math.max(...points.map((point) => point.y));
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const marginX = geometry.width < 520 ? 36 : 58;
    const marginTop = 56;
    const marginBottom = geometry.width < 520 ? 82 : 72;
    const scale = state.visible.length === 1
      ? 2.2
      : Math.min(
        (geometry.width - marginX * 2) / spanX,
        (geometry.height - marginTop - marginBottom) / spanY,
      );
    state.view.scale = Math.max(0.6, Math.min(4, scale));
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2 + (marginTop - marginBottom) / (2 * state.view.scale);
    state.view.x = -(centerX - geometry.width / 2) * state.view.scale;
    state.view.y = -(centerY - geometry.height / 2) * state.view.scale;
    requestDraw();
  }

  function centerNode(index) {
    const geometry = canvasGeometry();
    const point = basePoint(index, geometry);
    state.view.scale = Math.max(1.25, Math.min(2.4, state.view.scale));
    state.view.x = -(point.x - geometry.width / 2) * state.view.scale;
    state.view.y = -(point.y - geometry.height / 2) * state.view.scale;
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
      ["All-corpus citations", node.citations.withinCorpusReceived, "Incoming links from the complete 1,712-paper snapshot"],
      ["External citations", node.citations.externalMax, "Largest indexed-provider count at snapshot time"],
      ["PageRank", compactNumber(node.centrality.pageRank, 6), "Directed PageRank in the complete snapshot"],
      ["Betweenness", compactNumber(node.centrality.betweennessApprox, 6), "Approximate betweenness in the complete snapshot"],
    ];
    return element("dl", { className: "publication-network-detail-metrics" }, descriptions.map(([label, value, title]) =>
      element("div", {}, [
        element("dt", { text: label, attributes: { title } }),
        element("dd", { text: value }),
      ])));
  }

  function citationList(indices, emptyText) {
    if (!indices.length) return element("p", { className: "publication-network-detail-muted", text: emptyText });
    const sorted = [...indices].sort((left, right) =>
      audiotactileReceived[right] - audiotactileReceived[left]
      || (nodes[left].year || 9999) - (nodes[right].year || 9999));
    return element("ul", { className: "publication-network-citation-list" }, sorted.map((index) => {
      const button = element("button", {
        text: `${nodes[index].title} (${authorYear(nodes[index])})`,
        attributes: { type: "button" },
      });
      button.addEventListener("click", () => {
        controls.search.value = "";
        updateVisible();
        selectNode(index, canvas);
      });
      return element("li", {}, button);
    }));
  }

  function connectionDisclosure(label, indices, emptyText) {
    const disclosure = element("details", { className: "publication-network-connection-group" });
    disclosure.append(element("summary", {}, [
      element("span", { text: label }),
      element("strong", { text: indices.length }),
    ]));
    disclosure.append(element("div", { className: "publication-network-connection-list" }, [
      citationList(indices, emptyText),
    ]));
    return disclosure;
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

  function moreDetails(node) {
    const disclosure = element("details", { className: "publication-network-more-details" });
    disclosure.append(element("summary", { text: "Abstract, evidence notes, and full-corpus metrics" }));
    const content = element("div", { className: "publication-network-more-details-body" });
    const abstractChildren = [];
    if (node.abstract.status === "available" && node.abstract.text) {
      abstractChildren.push(element("p", { text: node.abstract.text }));
      abstractChildren.push(element("small", { text: `${node.abstract.source} · ${node.abstract.license}. ${node.abstract.caveat}` }));
    } else {
      abstractChildren.push(element("p", { className: "publication-network-detail-muted", text: node.abstract.caveat || "Abstract unavailable in this public snapshot." }));
    }
    content.append(
      makeSection("Abstract", abstractChildren),
      makeSection("Evidence classification", [
        element("p", { text: node.modality.audiotactile.basis }),
        node.modality.visuotactile?.status === "provisional_keyword_candidate"
          ? element("small", { text: "This paper also matched a provisional visuotactile keyword screen; that separate modality has not been manually verified." })
          : null,
      ]),
      makeSection("Complete-corpus metrics", [
        makeMetricGrid(node),
        element("small", { text: "These values describe position inside the dated 1,712-paper discovery corpus. They are navigation aids, not study-quality scores." }),
      ]),
    );
    disclosure.append(content);
    return disclosure;
  }

  function renderDetail(index) {
    const node = nodes[index];
    detailTitle.textContent = node.title;
    detailKicker.textContent = authorYear(node);
    const badges = [
      makeBadge("Audiotactile · manually verified", "publication-network-badge-at"),
      makeBadge(paperKind(node)),
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

    const connectionSummary = element("dl", { className: "publication-network-connection-summary" }, [
      element("div", {}, [element("dt", { text: "Cited by here" }), element("dd", { text: audiotactileReceived[index] })]),
      element("div", {}, [element("dt", { text: "References here" }), element("dd", { text: audiotactileReferences[index] })]),
    ]);
    const connections = makeSection("Connections in the verified map", [
      connectionSummary,
      connectionDisclosure("Papers that cite this paper", audiotactileIncoming[index], "No later verified audiotactile paper cites this paper in the snapshot."),
      connectionDisclosure("Verified papers referenced", audiotactileOutgoing[index], "This paper has no outgoing link to another verified audiotactile paper in the snapshot."),
    ]);

    const records = node.toolkit.records || [];
    const toolkit = records.length
      ? makeSection("PPS Toolkit parameters", records.map(toolkitRecord))
      : makeSection("PPS Toolkit parameters", [
        element("p", { className: "publication-network-detail-muted", text: "No toolkit parameter audit is joined to this paper by exact DOI." }),
      ]);

    detailBody.replaceChildren(overview, connections, toolkit, moreDetails(node));
  }

  function selectNode(index, trigger = canvas) {
    if (!Number.isInteger(index) || !state.visibleSet.has(index)) return;
    if (controls.search.value) {
      controls.search.value = "";
      updateVisible();
    }
    state.selected = index;
    state.lastFocus = trigger;
    state.lastFocusNode = trigger.classList?.contains("publication-network-result-button") ? index : null;
    renderDetail(index);
    resultPanel.hidden = true;
    detail.hidden = false;
    stage.classList.add("detail-open");
    renderResults();
    updateStatus();
    centerNode(index);
    requestAnimationFrame(() => {
      resizeCanvas();
      detail.focus({ preventScroll: true });
      if (window.matchMedia("(max-width: 760px)").matches) {
        detail.scrollIntoView({ block: "start", behavior: "smooth" });
      }
    });
  }

  function closeDetail({ restoreFocus = true } = {}) {
    state.selected = null;
    detail.hidden = true;
    resultPanel.hidden = false;
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

  controls.search.addEventListener("input", () => updateVisible({ resetView: true }));
  for (const input of controls.layout) input.addEventListener("change", () => updateVisible({ resetView: true }));
  controls.resultsSort.addEventListener("change", renderResults);
  resetButton.addEventListener("click", () => {
    controls.search.value = "";
    controls.resultsSort.value = "audiotactileReceived";
    for (const input of controls.layout) input.checked = input.value === "structure";
    closeDetail({ restoreFocus: false });
    updateVisible({ resetView: true });
  });

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
    fullscreenButton.textContent = document.fullscreenElement === shell ? "Exit expanded map" : "Expand map";
    fullscreenButton.setAttribute("aria-label", fullscreenButton.textContent);
    requestAnimationFrame(() => {
      resizeCanvas();
      fitView();
    });
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
      selectNode(state.selected ?? sortResults(state.visible)[0], canvas);
      return;
    }
    const ordered = sortResults(state.visible);
    const current = ordered.indexOf(state.selected);
    const direction = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
    const origin = current === -1 ? (direction > 0 ? -1 : 0) : current;
    const next = ordered[(origin + direction + ordered.length) % ordered.length];
    selectNode(next, canvas);
  });
  detail.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDetail();
    }
  });

  const resizeObserver = new ResizeObserver(resizeCanvas);
  resizeObserver.observe(mapPane);
  const themeObserver = new MutationObserver(requestDraw);
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  loading.hidden = true;
  root.dataset.publicationNetworkState = "ready";
  root.dataset.publicationNetworkNodes = String(nodes.length);
  root.dataset.publicationNetworkEdges = String(edges.length);
  root.dataset.publicationNetworkAudiotactileNodes = String(verifiedAudiotactile.length);
  root.dataset.publicationNetworkAudiotactileEdges = String(audiotactileEdges.length);
  updateVisible({ resetView: true });
  resizeCanvas();
  root.dispatchEvent(new CustomEvent("pps:publication-network-ready", {
    bubbles: true,
    detail: {
      nodes: nodes.length,
      edges: edges.length,
      audiotactileNodes: verifiedAudiotactile.length,
      audiotactileEdges: audiotactileEdges.length,
    },
  }));
}
