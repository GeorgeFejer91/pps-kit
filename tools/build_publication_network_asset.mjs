#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");
const DEFAULT_SNAPSHOT = path.join(
  REPO_ROOT,
  "data/publication_network/citation_snapshot.v1.json",
);
const DEFAULT_OUTPUT = path.join(
  REPO_ROOT,
  "src/peripersonal_space_toolkit/dashboard/publication_network.v3.json",
);
const CITATION_OVERLAY_PATHS = [
  "data/publication_network/openalex_audiotactile_citation_overlay.20260808.json",
  "data/publication_network/primary_source_citation_overlay.20260808.json",
].map((relativePath) => path.join(REPO_ROOT, relativePath));
const COVERAGE_PATH = path.join(
  REPO_ROOT,
  "assets/preloads/audiotactile_literature_coverage.json",
);
const MANUAL_REVIEW_DIR = path.join(
  REPO_ROOT,
  "For-AI/audiotactile-paper-metadata-audit/manual_reviews",
);

const SOURCE_EXPECTED = Object.freeze({
  nodes: 1712,
  edges: 10109,
  audiotactileConfirmed: 101,
  toolkitRecordJoins: 73,
  toolkitNodeJoins: 69,
});

const NETWORK_EXPECTED = Object.freeze({
  nodes: 94,
  edges: 750,
  audiotactileConfirmed: 90,
  laterAuditAdditions: 4,
  toolkitRecordJoins: 69,
  toolkitInScopeRecordJoins: 68,
  toolkitNodeJoins: 65,
  toolkitInScopeNodeJoins: 64,
  toolkitRunnableNodes: 15,
  toolkitRunnableRecords: 17,
  toolkitSupportedIncompleteNodes: 49,
  toolkitNotAssessedNodes: 29,
  toolkitAdjacentConflictNodes: 1,
  toolkitManualReviewRecords: 24,
  toolkitManualReviewNodes: 21,
  connectedNodes: 91,
  isolatedNodes: 3,
  weakComponents: 4,
  abstractsAvailable: 37,
  abstractsSourceLinkOnly: 48,
  abstractsNotAvailable: 9,
});

const SOURCE_SCHEMA = "pps-publication-citation-source.v1";
const ASSET_SCHEMA = "pps-publication-citation-network.v3";
const OVERLAY_SCHEMA = "pps-publication-citation-overlay.v1";
const SNAPSHOT_ID = "pps-citation-network-20260807";
const SNAPSHOT_DATE = "2026-08-07";
const GENERATOR_VERSION = "3.4.0";
const LAYOUT_MARGIN = 0.045;
const NODE_RADIUS_MIN = 0.009;
const NODE_RADIUS_MAX = 0.024;
const NODE_CLEARANCE = 0.015;
const TOPOLOGY_ITERATIONS = 500;

function usage() {
  return `Build the PPS publication/citation network asset.

Usage:
  node tools/build_publication_network_asset.mjs [options]

Options:
  --source-bundle <dir>    Import the original citation-network bundle.
  --source-snapshot <file> Read a public-safe source snapshot (default: tracked snapshot).
  --snapshot-output <file> Write imported source snapshot here.
  --output <file>          Write the generated dashboard JSON here.
  --validate-only          Validate inputs and generated data without writing output.
  --pretty                 Pretty-print the dashboard asset (default is compact JSON).
  --help                   Show this help.

With --source-bundle, the importer reads data/nodes.json, data/edges.json and,
when present, data/raw/openalex_manual_seeds.json. The tracked source snapshot
contains no raw provider payloads and republishes abstract text only where an
OpenAlex record gives explicit CC0 metadata provenance.
`;
}

function parseArgs(argv) {
  const options = {
    sourceBundle: "",
    sourceSnapshot: DEFAULT_SNAPSHOT,
    snapshotOutput: "",
    output: DEFAULT_OUTPUT,
    validateOnly: false,
    pretty: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const takeValue = () => {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`${arg} requires a value`);
      index += 1;
      return path.resolve(value);
    };
    if (arg === "--source-bundle") options.sourceBundle = takeValue();
    else if (arg === "--source-snapshot") options.sourceSnapshot = takeValue();
    else if (arg === "--snapshot-output") options.snapshotOutput = takeValue();
    else if (arg === "--output") options.output = takeValue();
    else if (arg === "--validate-only") options.validateOnly = true;
    else if (arg === "--pretty") options.pretty = true;
    else if (arg === "--help") {
      process.stdout.write(usage());
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}\n\n${usage()}`);
    }
  }

  if (options.sourceBundle && !options.snapshotOutput) {
    options.snapshotOutput = DEFAULT_SNAPSHOT;
  }
  return options;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJson(file, value, pretty = true) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const space = pretty ? 2 : 0;
  fs.writeFileSync(file, `${JSON.stringify(value, null, space)}\n`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function normalizeDoi(value) {
  return String(value || "")
    .trim()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "")
    .replace(/[\s.]+$/g, "")
    .toLowerCase();
}

function normalizeWhitespace(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function reconstructOpenAlexAbstract(index) {
  if (!index || typeof index !== "object") return "";
  const words = [];
  for (const [word, positions] of Object.entries(index)) {
    for (const position of positions || []) words[position] = word;
  }
  return normalizeWhitespace(words.filter((word) => word !== undefined).join(" "));
}

function openAlexShort(value) {
  return String(value || "").match(/W\d+$/)?.[0] || "";
}

function fnv1a(value) {
  let hash = 0x811c9dc5;
  for (const char of String(value)) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function hashUnit(value) {
  return fnv1a(value) / 0xffffffff;
}

function roundCoordinate(value) {
  return Number(Math.max(0, Math.min(1, value)).toFixed(6));
}

function classifyVisuotactile(node) {
  const text = [
    node.title,
    node.abstract,
    ...(node.keywords || []),
    ...(node.topics || []),
  ].join("\n");
  const patterns = [
    ["visuotactile", /\bvisuo[- ]?tactile\b/i],
    ["visual-tactile", /\bvisual[- ]?tactile\b/i],
    ["visual and tactile", /\bvisual\s+(?:and|&)\s+tactile\b/i],
    ["tactile and visual", /\btactile\s+(?:and|&)\s+visual\b/i],
  ];
  const terms = patterns.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
  if (terms.length) {
    return {
      status: "provisional_keyword_candidate",
      verified: false,
      basis: "Automated lexical screen only; manual visuotactile PPS verification is required.",
      terms,
    };
  }
  return {
    status: "not_classified",
    verified: false,
    basis: "No verified visuotactile audit is available for this corpus snapshot.",
    terms: [],
  };
}

function safeAbstract(node, openAlexByDoi, openAlexById) {
  const openAlex = openAlexByDoi.get(normalizeDoi(node.doi))
    || (node.openalex_ids || []).map(openAlexShort).map((id) => openAlexById.get(id)).find(Boolean);
  const text = reconstructOpenAlexAbstract(openAlex?.abstract_inverted_index);
  if (text) {
    return {
      status: "available",
      text,
      source: "OpenAlex",
      sourceUrl: openAlex?.id || "https://openalex.org/",
      license: "CC0-1.0",
      caveat: "OpenAlex metadata is released under CC0; copyright in the underlying publication remains with its rights holder.",
    };
  }
  if (node.abstract) {
    return {
      status: "source_link_only",
      text: null,
      source: "Merged bibliographic indexes",
      sourceUrl: node.url || "",
      license: null,
      caveat: "An abstract was indexed in the research snapshot, but its selected-text provenance and reuse terms cannot be established; follow the publication link instead.",
    };
  }
  return {
    status: "not_available",
    text: null,
    source: "",
    sourceUrl: node.url || "",
    license: null,
    caveat: "No abstract was available in the source snapshot.",
  };
}

function createSourceSnapshot(bundleDir) {
  const nodePath = path.join(bundleDir, "data/nodes.json");
  const edgePath = path.join(bundleDir, "data/edges.json");
  assert(fs.existsSync(nodePath), `Missing source nodes: ${nodePath}`);
  assert(fs.existsSync(edgePath), `Missing source edges: ${edgePath}`);

  const originalNodes = readJson(nodePath);
  const originalEdges = readJson(edgePath);
  const openAlexPath = path.join(bundleDir, "data/raw/openalex_manual_seeds.json");
  const openAlex = fs.existsSync(openAlexPath) ? readJson(openAlexPath) : [];
  const openAlexByDoi = new Map();
  const openAlexById = new Map();
  for (const record of openAlex) {
    const doi = normalizeDoi(record.doi || record.ids?.doi);
    if (doi) openAlexByDoi.set(doi, record);
    const id = openAlexShort(record.id);
    if (id) openAlexById.set(id, record);
  }

  const nodes = originalNodes
    .map((node) => ({
      id: node.id,
      title: normalizeWhitespace(node.title),
      year: Number.isInteger(node.year) ? node.year : null,
      publicationDate: node.publication_date || "",
      doi: normalizeDoi(node.doi),
      pmid: String(node.pmid || ""),
      openAlexIds: [...(node.openalex_ids || [])].sort(),
      semanticScholarIds: [...(node.semantic_scholar_ids || [])].sort(),
      authors: [...(node.authors || [])],
      venue: normalizeWhitespace(node.venue),
      abstract: safeAbstract(node, openAlexByDoi, openAlexById),
      keywords: [...(node.keywords || [])].sort(),
      topics: [...(node.topics || [])].sort(),
      corpus: {
        tier: node.corpus_tier || "pps_candidate",
        reason: node.corpus_reason || "",
        theme: node.theme || "unclassified",
        documentRole: node.document_role || "unknown",
        paradigmFamily: node.paradigm_family || "",
      },
      modality: {
        audiotactile: node.audiotactile_status === "confirmed"
          ? {
              status: "confirmed",
              verified: true,
              basis: node.audiotactile_reason || "Manually confirmed in the citation-network audit.",
            }
          : {
              status: "not_confirmed",
              verified: false,
              basis: node.audiotactile_reason || "Not part of the manually confirmed audiotactile subset.",
            },
        visuotactile: classifyVisuotactile(node),
      },
      citations: {
        withinCorpusReceived: Number(node.internal_citations_received || 0),
        withinCorpusReferences: Number(node.internal_references_made || 0),
        externalMax: Number(node.citations_external_max || 0),
        providers: {
          openAlex: Number(node.citations_openalex || 0),
          semanticScholar: Number(node.citations_semantic_scholar || 0),
          europePmc: Number(node.citations_europe_pmc || 0),
        },
      },
      centrality: {
        pageRank: Number(node.pagerank || 0),
        betweennessApprox: Number(node.betweenness_approx || 0),
        influence: Number(node.influence_score || 0),
        component: Number(node.component ?? -1),
      },
      links: {
        primary: node.url || "",
        doi: node.doi ? `https://doi.org/${normalizeDoi(node.doi)}` : "",
        openAccess: node.open_access_url || "",
      },
      metadata: {
        sources: [...(node.sources || [])].sort(),
        conflict: Boolean(node.metadata_conflict),
        retracted: Boolean(node.is_retracted),
      },
    }))
    .sort((left, right) => left.id.localeCompare(right.id));

  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = originalEdges
    .map((edge) => ({
      source: edge.source,
      target: edge.target,
      provenance: edge.provenance || "unspecified",
    }))
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .sort((left, right) => left.source.localeCompare(right.source)
      || left.target.localeCompare(right.target)
      || left.provenance.localeCompare(right.provenance));

  return {
    schema: SOURCE_SCHEMA,
    snapshotId: SNAPSHOT_ID,
    builtOn: SNAPSHOT_DATE,
    scopeClaim: "Maximum-coverage, multi-index PPS-explicit corpus snapshot with manually validated audiotactile studies and citation context; it is not a claim of universal bibliographic completeness.",
    sourceMethodology: {
      originalBundle: SNAPSHOT_ID,
      edgeDirection: "source publication cites target publication",
      abstractPolicy: "Only text reconstructed from an OpenAlex-attributed metadata record is included under OpenAlex's CC0 terms; copyright in the underlying publication remains with its rights holder. Other indexed abstracts are represented by status and source links, not copied text.",
      audiotactilePolicy: "Only the original bundle's manually confirmed subset is marked verified.",
      visuotactilePolicy: "Lexical matches are provisional candidates and never marked verified without a dedicated manual audit.",
    },
    nodes,
    edges,
  };
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function mean(values) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
}

function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const midpoint = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[midpoint]
    : (sorted[midpoint - 1] + sorted[midpoint]) / 2;
}

function normalizedValues(values, logarithmic = false) {
  const transformed = values.map((value) => logarithmic ? Math.log1p(value) : value);
  const minimum = Math.min(...transformed);
  const maximum = Math.max(...transformed);
  const range = maximum - minimum;
  if (!range) return transformed.map(() => 0);
  return transformed.map((value) => (value - minimum) / range);
}

function rankValues(values) {
  const sorted = values
    .map((value, index) => ({ value, index }))
    .sort((left, right) => left.value - right.value || left.index - right.index);
  const ranks = Array(values.length).fill(0);
  for (let start = 0; start < sorted.length;) {
    let end = start + 1;
    while (end < sorted.length && sorted[end].value === sorted[start].value) end += 1;
    const rank = (start + end - 1) / 2;
    for (let index = start; index < end; index += 1) ranks[sorted[index].index] = rank;
    start = end;
  }
  return ranks;
}

function correlation(left, right) {
  if (!left.length || left.length !== right.length) return 0;
  const leftMean = mean(left);
  const rightMean = mean(right);
  let numerator = 0;
  let leftSquare = 0;
  let rightSquare = 0;
  for (let index = 0; index < left.length; index += 1) {
    const leftDelta = left[index] - leftMean;
    const rightDelta = right[index] - rightMean;
    numerator += leftDelta * rightDelta;
    leftSquare += leftDelta ** 2;
    rightSquare += rightDelta ** 2;
  }
  return leftSquare && rightSquare ? numerator / Math.sqrt(leftSquare * rightSquare) : 0;
}

function spearman(left, right) {
  return correlation(rankValues(left), rankValues(right));
}

function weakComponents(adjacency, nodes) {
  const visited = new Set();
  const components = [];
  for (let start = 0; start < nodes.length; start += 1) {
    if (visited.has(start)) continue;
    const queue = [start];
    visited.add(start);
    const component = [];
    while (queue.length) {
      const index = queue.pop();
      component.push(index);
      for (const neighbour of adjacency[index]) {
        if (visited.has(neighbour)) continue;
        visited.add(neighbour);
        queue.push(neighbour);
      }
    }
    component.sort((left, right) => nodes[left].id.localeCompare(nodes[right].id));
    components.push(component);
  }
  components.sort((left, right) => right.length - left.length
    || nodes[left[0]].id.localeCompare(nodes[right[0]].id));
  return components;
}

function inducedPageRank(nodeCount, directedEdges, outgoingDegree) {
  const damping = 0.85;
  let scores = Array(nodeCount).fill(1 / nodeCount);
  for (let iteration = 0; iteration < 100; iteration += 1) {
    const dangling = scores.reduce((total, score, index) =>
      total + (outgoingDegree[index] ? 0 : score), 0);
    const next = Array(nodeCount).fill((1 - damping) / nodeCount
      + (damping * dangling) / nodeCount);
    for (const [source, target] of directedEdges) {
      next[target] += damping * scores[source] / outgoingDegree[source];
    }
    scores = next;
  }
  return scores;
}

function buildNetworkMetrics(nodes, edges) {
  const nodeIndex = new Map(nodes.map((node, index) => [node.id, index]));
  const directedEdges = edges.map((edge) => [
    nodeIndex.get(edge.source),
    nodeIndex.get(edge.target),
  ]);
  const incomingDegree = Array(nodes.length).fill(0);
  const outgoingDegree = Array(nodes.length).fill(0);
  const weakEdgeKeys = new Set();
  for (const [source, target] of directedEdges) {
    outgoingDegree[source] += 1;
    incomingDegree[target] += 1;
    weakEdgeKeys.add(source < target ? `${source}:${target}` : `${target}:${source}`);
  }
  const weakEdges = [...weakEdgeKeys]
    .map((key) => key.split(":").map(Number))
    .sort((left, right) => left[0] - right[0] || left[1] - right[1]);
  const adjacency = Array.from({ length: nodes.length }, () => new Set());
  for (const [source, target] of weakEdges) {
    adjacency[source].add(target);
    adjacency[target].add(source);
  }
  const weakDegree = adjacency.map((neighbours) => neighbours.size);
  const components = weakComponents(adjacency, nodes);
  const component = Array(nodes.length).fill(-1);
  components.forEach((indices, componentIndex) => {
    for (const index of indices) component[index] = componentIndex;
  });
  const pageRank = inducedPageRank(nodes.length, directedEdges, outgoingDegree);
  const citations = nodes.map((node) => node.citations.withinCorpusReceived);
  const normalizedCitations = normalizedValues(citations, true);
  const normalizedPageRank = normalizedValues(pageRank);
  const normalizedIncoming = normalizedValues(incomingDegree, true);
  const prominence = nodes.map((node, index) =>
    (0.55 * normalizedCitations[index])
      + (0.30 * normalizedPageRank[index])
      + (0.15 * normalizedIncoming[index]));
  const minimumArea = NODE_RADIUS_MIN ** 2;
  const areaRange = NODE_RADIUS_MAX ** 2 - minimumArea;
  const radii = normalizedIncoming.map((citation) =>
    Math.sqrt(minimumArea + areaRange * citation));
  return {
    nodeIndex,
    directedEdges,
    weakEdges,
    adjacency,
    incomingDegree,
    outgoingDegree,
    weakDegree,
    components,
    component,
    pageRank,
    prominence,
    radii,
  };
}

function clampPositions(positions, radii) {
  for (let index = 0; index < positions.length; index += 1) {
    const minimum = LAYOUT_MARGIN + radii[index];
    const maximum = 1 - LAYOUT_MARGIN - radii[index];
    positions[index].x = clamp(positions[index].x, minimum, maximum);
    positions[index].y = clamp(positions[index].y, minimum, maximum);
  }
}

function collisionDirection(left, right) {
  const angle = hashUnit(`${left}:${right}:collision`) * Math.PI * 2;
  return { x: Math.cos(angle), y: Math.sin(angle) };
}

function resolveCollisions(positions, radii, passes = 1) {
  let maximumOverlap = 0;
  const requiredExtra = NODE_CLEARANCE + 0.000004;
  for (let pass = 0; pass < passes; pass += 1) {
    maximumOverlap = 0;
    for (let left = 0; left < positions.length; left += 1) {
      for (let right = left + 1; right < positions.length; right += 1) {
        let dx = positions[left].x - positions[right].x;
        let dy = positions[left].y - positions[right].y;
        let distance = Math.hypot(dx, dy);
        const required = radii[left] + radii[right] + requiredExtra;
        const overlap = required - distance;
        if (overlap <= 0) continue;
        maximumOverlap = Math.max(maximumOverlap, overlap);
        if (distance < 1e-12) {
          const direction = collisionDirection(left, right);
          dx = direction.x;
          dy = direction.y;
          distance = 1;
        }
        const shift = overlap / 2 + 1e-7;
        const unitX = dx / distance;
        const unitY = dy / distance;
        positions[left].x += unitX * shift;
        positions[left].y += unitY * shift;
        positions[right].x -= unitX * shift;
        positions[right].y -= unitY * shift;
      }
    }
    clampPositions(positions, radii);
  }
  return maximumOverlap;
}

function polishCollisions(positions, radii) {
  for (let iteration = 0; iteration < 400; iteration += 1) {
    if (resolveCollisions(positions, radii, 1) < 1e-9) break;
  }
}

function topologyNodeOrder(left, right, metrics, nodes) {
  return metrics.prominence[right] - metrics.prominence[left]
    || nodes[left].id.localeCompare(nodes[right].id);
}

function createTopologyLayout(nodes, metrics) {
  const count = nodes.length;
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const order = Array.from({ length: count }, (_, index) => index)
    .sort((left, right) => topologyNodeOrder(left, right, metrics, nodes));
  const rank = Array(count).fill(0);
  order.forEach((nodeIndex, index) => { rank[nodeIndex] = index; });
  const positions = nodes.map((node, index) => {
    const radial = 0.055 + 0.405 * Math.sqrt(rank[index] / Math.max(1, count - 1));
    const angle = rank[index] * goldenAngle + 0.17;
    return {
      x: 0.5 + radial * Math.cos(angle),
      y: 0.5 + radial * Math.sin(angle),
    };
  });
  const velocities = nodes.map(() => ({ x: 0, y: 0 }));
  clampPositions(positions, metrics.radii);

  for (let iteration = 0; iteration < TOPOLOGY_ITERATIONS; iteration += 1) {
    const forces = nodes.map(() => ({ x: 0, y: 0 }));
    for (let left = 0; left < count; left += 1) {
      for (let right = left + 1; right < count; right += 1) {
        let dx = positions[left].x - positions[right].x;
        let dy = positions[left].y - positions[right].y;
        let distance = Math.hypot(dx, dy);
        if (distance < 1e-12) {
          const direction = collisionDirection(left, right);
          dx = direction.x * 1e-6;
          dy = direction.y * 1e-6;
          distance = 1e-6;
        }
        const magnitude = 0.0000055 / (distance ** 2 + 0.0018);
        const forceX = (dx / distance) * magnitude;
        const forceY = (dy / distance) * magnitude;
        forces[left].x += forceX;
        forces[left].y += forceY;
        forces[right].x -= forceX;
        forces[right].y -= forceY;
      }
    }
    for (const [source, target] of metrics.weakEdges) {
      const dx = positions[source].x - positions[target].x;
      const dy = positions[source].y - positions[target].y;
      const distance = Math.max(1e-12, Math.hypot(dx, dy));
      const ideal = 0.21;
      const strength = 0.0035
        / (Math.max(1, metrics.weakDegree[source] * metrics.weakDegree[target]) ** 0.22);
      const magnitude = -strength * (distance - ideal);
      const forceX = (dx / distance) * magnitude;
      const forceY = (dy / distance) * magnitude;
      forces[source].x += forceX;
      forces[source].y += forceY;
      forces[target].x -= forceX;
      forces[target].y -= forceY;
    }
    for (let index = 0; index < count; index += 1) {
      forces[index].x += 0.008 * (0.5 - positions[index].x);
      forces[index].y += 0.008 * (0.5 - positions[index].y);
    }
    const temperature = 0.0185 * (1 - iteration / TOPOLOGY_ITERATIONS) + 0.0015;
    for (let index = 0; index < count; index += 1) {
      velocities[index].x = 0.78 * velocities[index].x + forces[index].x;
      velocities[index].y = 0.78 * velocities[index].y + forces[index].y;
      const speed = Math.hypot(velocities[index].x, velocities[index].y);
      if (speed > temperature) {
        velocities[index].x *= temperature / speed;
        velocities[index].y *= temperature / speed;
      }
      positions[index].x += velocities[index].x;
      positions[index].y += velocities[index].y;
    }
    clampPositions(positions, metrics.radii);
    resolveCollisions(positions, metrics.radii, 2);
  }
  polishCollisions(positions, metrics.radii);
  return positions.map((position) => ({
    x: roundCoordinate(position.x),
    y: roundCoordinate(position.y),
  }));
}

function createTimelineLayout(nodes, metrics, topology) {
  const years = nodes.map((node) => node.year).filter(Number.isInteger);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const yearRange = Math.max(1, maxYear - minYear);
  const timelineMinimum = LAYOUT_MARGIN + NODE_RADIUS_MAX + 0.01;
  const timelineMaximum = 1 - timelineMinimum;
  const targetX = nodes.map((node) => {
    const normalizedYear = Number.isInteger(node.year)
      ? (node.year - minYear) / yearRange
      : 1;
    const jitter = (hashUnit(`${node.id}:timeline`) - 0.5) * 0.009;
    return clamp(
      timelineMinimum + normalizedYear * (timelineMaximum - timelineMinimum) + jitter,
      timelineMinimum,
      timelineMaximum,
    );
  });
  const positions = topology.map((position, index) => ({
    x: targetX[index],
    y: position.y,
  }));
  const velocities = nodes.map(() => ({ x: 0, y: 0 }));
  clampPositions(positions, metrics.radii);
  const iterations = Math.floor(TOPOLOGY_ITERATIONS / 2);
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const forces = nodes.map(() => ({ x: 0, y: 0 }));
    for (let left = 0; left < nodes.length; left += 1) {
      for (let right = left + 1; right < nodes.length; right += 1) {
        let dx = positions[left].x - positions[right].x;
        let dy = positions[left].y - positions[right].y;
        let distance = Math.hypot(dx, dy);
        if (distance < 1e-12) {
          const direction = collisionDirection(left, right);
          dx = direction.x * 1e-6;
          dy = direction.y * 1e-6;
          distance = 1e-6;
        }
        const magnitude = (0.00011
          * (metrics.radii[left] + metrics.radii[right] + 0.025) ** 2)
          / (distance ** 2 + 0.001);
        const forceX = (dx / distance) * magnitude;
        const forceY = (dy / distance) * magnitude;
        forces[left].x += forceX;
        forces[left].y += forceY;
        forces[right].x -= forceX;
        forces[right].y -= forceY;
      }
    }
    for (const [source, target] of metrics.weakEdges) {
      const dy = positions[source].y - positions[target].y;
      const forceY = -0.0025 * dy
        / (Math.max(1, metrics.weakDegree[source] * metrics.weakDegree[target]) ** 0.08);
      forces[source].y += forceY;
      forces[target].y -= forceY;
    }
    const temperature = 0.016 * (1 - iteration / iterations) + 0.0018;
    for (let index = 0; index < nodes.length; index += 1) {
      forces[index].x += 0.045 * (targetX[index] - positions[index].x);
      forces[index].y += 0.0012 * (0.5 - positions[index].y);
      velocities[index].x = 0.76 * velocities[index].x + forces[index].x;
      velocities[index].y = 0.76 * velocities[index].y + forces[index].y;
      const speed = Math.hypot(velocities[index].x, velocities[index].y);
      if (speed > temperature) {
        velocities[index].x *= temperature / speed;
        velocities[index].y *= temperature / speed;
      }
      positions[index].x += velocities[index].x;
      positions[index].y += velocities[index].y;
    }
    clampPositions(positions, metrics.radii);
    resolveCollisions(positions, metrics.radii, 2);
  }
  polishCollisions(positions, metrics.radii);
  return {
    positions: positions.map((position) => ({
      x: roundCoordinate(position.x),
      y: roundCoordinate(position.y),
    })),
    minYear,
    maxYear,
  };
}

function layoutQuality(positions, metrics) {
  const distances = Array.from({ length: positions.length }, () => Array(positions.length).fill(0));
  let minimumClearance = Number.POSITIVE_INFINITY;
  let clearanceViolations = 0;
  let minimumCenterDistance = Number.POSITIVE_INFINITY;
  const nonNeighbourDistances = [];
  const principalComponentNonNeighbourDistances = [];
  for (let left = 0; left < positions.length; left += 1) {
    for (let right = left + 1; right < positions.length; right += 1) {
      const distance = Math.hypot(
        positions[left].x - positions[right].x,
        positions[left].y - positions[right].y,
      );
      distances[left][right] = distance;
      distances[right][left] = distance;
      minimumCenterDistance = Math.min(minimumCenterDistance, distance);
      const clearance = distance - metrics.radii[left] - metrics.radii[right];
      minimumClearance = Math.min(minimumClearance, clearance);
      if (clearance < NODE_CLEARANCE - 0.000002) clearanceViolations += 1;
      if (!metrics.adjacency[left].has(right)) {
        nonNeighbourDistances.push(distance);
        if (metrics.component[left] === 0 && metrics.component[right] === 0) {
          principalComponentNonNeighbourDistances.push(distance);
        }
      }
    }
  }
  const edgeDistances = metrics.weakEdges.map(([source, target]) => distances[source][target]);
  const radialDistances = positions.map((position) =>
    Math.hypot(position.x - 0.5, position.y - 0.5));
  const connectedRadialDistances = radialDistances.filter((value, index) => metrics.weakDegree[index] > 0);
  const isolatedRadialDistances = radialDistances.filter((value, index) => metrics.weakDegree[index] === 0);
  const principalIndices = positions.map((_, index) => index)
    .filter((index) => metrics.component[index] === 0);
  const principalX = principalIndices.map((index) => positions[index].x);
  const principalY = principalIndices.map((index) => positions[index].y);
  const principalGridCells = new Set(principalIndices.map((index) => {
    const column = Math.min(5, Math.floor(positions[index].x * 6));
    const row = Math.min(5, Math.floor(positions[index].y * 6));
    return `${column}:${row}`;
  }));
  const nearestNeighbourDistances = positions.map((position, index) => Math.min(
    ...positions.map((other, otherIndex) => otherIndex === index
      ? Number.POSITIVE_INFINITY
      : Math.hypot(position.x - other.x, position.y - other.y)),
  ));
  const isolatedNearBoundary = positions.filter((position, index) =>
    metrics.weakDegree[index] === 0
      && Math.min(position.x, 1 - position.x, position.y, 1 - position.y) < 0.09).length;
  return {
    minimumCenterDistance: Number(minimumCenterDistance.toFixed(6)),
    minimumClearance: Number(minimumClearance.toFixed(6)),
    clearanceViolations,
    edgeMeanDistance: Number(mean(edgeDistances).toFixed(6)),
    edgeMedianDistance: Number(median(edgeDistances).toFixed(6)),
    nonNeighbourMeanDistance: Number(mean(nonNeighbourDistances).toFixed(6)),
    principalComponentNonNeighbourMeanDistance: Number(mean(principalComponentNonNeighbourDistances).toFixed(6)),
    edgeToPrincipalNonNeighbourRatio: Number((mean(edgeDistances)
      / mean(principalComponentNonNeighbourDistances)).toFixed(6)),
    prominenceRadialSpearman: Number(spearman(metrics.prominence, radialDistances).toFixed(6)),
    connectedMeanRadialDistance: Number(mean(connectedRadialDistances).toFixed(6)),
    isolatedMeanRadialDistance: Number(mean(isolatedRadialDistances).toFixed(6)),
    medianNearestNeighbourDistance: Number(median(nearestNeighbourDistances).toFixed(6)),
    principalComponentSpanX: Number((Math.max(...principalX) - Math.min(...principalX)).toFixed(6)),
    principalComponentSpanY: Number((Math.max(...principalY) - Math.min(...principalY)).toFixed(6)),
    principalComponentOccupiedGridCells6x6: principalGridCells.size,
    isolatedNodesNearBoundary: isolatedNearBoundary,
    uniqueRoundedX: new Set(positions.map((position) => position.x.toFixed(4))).size,
    uniqueRoundedY: new Set(positions.map((position) => position.y.toFixed(4))).size,
    minNodeExtentX: Number(Math.min(...positions.map((position, index) =>
      position.x - metrics.radii[index])).toFixed(6)),
    maxNodeExtentX: Number(Math.max(...positions.map((position, index) =>
      position.x + metrics.radii[index])).toFixed(6)),
    minNodeExtentY: Number(Math.min(...positions.map((position, index) =>
      position.y - metrics.radii[index])).toFixed(6)),
    maxNodeExtentY: Number(Math.max(...positions.map((position, index) =>
      position.y + metrics.radii[index])).toFixed(6)),
  };
}

function createNetworkLayouts(nodes, edges) {
  const metrics = buildNetworkMetrics(nodes, edges);
  const topology = createTopologyLayout(nodes, metrics);
  const timeline = createTimelineLayout(nodes, metrics, topology);
  return {
    metrics,
    topology,
    timeline: timeline.positions,
    minYear: timeline.minYear,
    maxYear: timeline.maxYear,
    quality: {
      topology: layoutQuality(topology, metrics),
      timeline: layoutQuality(timeline.positions, metrics),
    },
  };
}

function loadToolkitAudits() {
  const coverage = readJson(COVERAGE_PATH);
  const reviews = fs.readdirSync(MANUAL_REVIEW_DIR)
    .filter((file) => file.endsWith(".json"))
    .sort()
    .map((file) => readJson(path.join(MANUAL_REVIEW_DIR, file)));
  return {
    coverage,
    coverageByDoi: coverage.literature_records
      .filter((record) => normalizeDoi(record.doi))
      .reduce((recordsByDoi, record) => {
        const doi = normalizeDoi(record.doi);
        const matches = recordsByDoi.get(doi) || [];
        matches.push(record);
        recordsByDoi.set(doi, matches);
        return recordsByDoi;
      }, new Map()),
    reviewsByRecordId: new Map(reviews.map((review) => [review.record_id, review])),
  };
}

function compactManualReview(review) {
  const segments = {};
  for (const [segment, fields] of Object.entries(review.segment_field_audit || {})) {
    segments[segment] = {};
    for (const [field, entry] of Object.entries(fields || {})) {
      segments[segment][field] = {
        status: entry.status || "source_unavailable",
        value: entry.value ?? "",
        pageOrSection: entry.page_or_section || "",
        evidenceNote: entry.evidence_note || "",
      };
    }
  }
  const assessment = review.profile_recreation_assessment || {};
  return {
    status: review.manual_review_status || "manual_review_completed",
    reviewedOn: review.review_date || "",
    confidenceScore: Number(review.confidence_score || 0),
    confidenceLabel: review.confidence_label || "",
    recreationAssessment: {
      assessment: assessment.assessment || "",
      reason: assessment.reason || "",
    },
    segments,
  };
}

function toolkitForNode(node, audits) {
  const records = audits.coverageByDoi.get(normalizeDoi(node.doi)) || [];
  if (!records.length) {
    return {
      joinStatus: "not_audited",
      status: "not_assessed",
      inScopeRecordCount: 0,
      records: [],
    };
  }
  const joinedRecords = records.map((record) => {
    const review = audits.reviewsByRecordId.get(record.record_id);
    return {
      recordId: record.record_id,
      citationShort: record.citation_short || "",
      coverageCategory: record.coverage_category || "",
      inScope: Boolean(record.coverage_category)
        && record.coverage_category !== "adjacent_out_of_scope",
      taskFamily: record.audiotactile_task_family || "",
      recreatable: Boolean(record.can_recreate_audiotactile_components_now),
      templateIds: [...(record.current_template_ids || [])],
      missingParameters: [...(record.missing_publication_parameters || [])],
      manualReview: review ? compactManualReview(review) : null,
    };
  }).sort((left, right) => left.recordId.localeCompare(right.recordId));
  const inScopeRecords = joinedRecords.filter((record) => record.inScope);
  const status = inScopeRecords.some((record) => record.recreatable)
    ? "runnable"
    : inScopeRecords.length
      ? "supported_incomplete"
      : "adjacent_scope_conflict";
  return {
    joinStatus: joinedRecords.some((record) => record.manualReview)
      ? "doi_matched_manual_parameter_review"
      : "doi_matched_literature_audit",
    status,
    inScopeRecordCount: inScopeRecords.length,
    records: joinedRecords,
  };
}

function countValues(values) {
  const counts = {};
  for (const value of values) counts[value] = (counts[value] || 0) + 1;
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function isInScopeToolkitRecord(record) {
  return record.inScope ?? (Boolean(record.coverageCategory)
    && record.coverageCategory !== "adjacent_out_of_scope");
}

function isCandidateNetworkPublication(node) {
  return node.corpus.documentRole !== "review"
    && (node.modality.audiotactile.verified
      || node.toolkit.records.some(isInScopeToolkitRecord));
}

function hasVerifiedDoiUrl(node) {
  const doi = normalizeDoi(node.doi);
  return /^10\.\d{4,9}\/\S+$/i.test(doi)
    && node.id === `doi:${doi}`
    && node.links?.doi === `https://doi.org/${doi}`;
}

function citationMetadataProviders(node) {
  const sources = new Set(node.metadata?.sources || []);
  const providers = node.citations?.providers || {};
  const available = [];
  if (sources.has("openalex")
      && node.openAlexIds?.length
      && Number.isFinite(providers.openAlex)
      && providers.openAlex >= 0) {
    available.push("OpenAlex");
  }
  if (sources.has("semantic_scholar")
      && node.semanticScholarIds?.length
      && Number.isFinite(providers.semanticScholar)
      && providers.semanticScholar >= 0) {
    available.push("Semantic Scholar");
  }
  if (sources.has("europe_pmc")
      && node.pmid
      && Number.isFinite(providers.europePmc)
      && providers.europePmc >= 0) {
    available.push("Europe PMC");
  }
  return available;
}

function hasCitationMetadata(node) {
  return citationMetadataProviders(node).length > 0;
}

function isNetworkPublication(node) {
  return isCandidateNetworkPublication(node)
    && hasVerifiedDoiUrl(node)
    && hasCitationMetadata(node);
}

function scopeForNode(node) {
  if (node.modality.audiotactile.verified) {
    return {
      provenance: "legacy_confirmed",
      basis: "Manually confirmed as audiotactile in the citation-corpus audit.",
    };
  }
  return {
    provenance: "later_exact_doi_audit",
    basis: "Added by an exact-DOI Toolkit literature audit with at least one non-adjacent audiotactile PPS task record.",
  };
}

function loadCitationOverlays(candidateIds, networkIds, candidateSnapshotEdges) {
  const existingKeys = new Set(candidateSnapshotEdges.map((edge) => `${edge.source}\u0000${edge.target}`));
  const overlays = [];
  let unionEdgeCount = candidateSnapshotEdges.length;
  for (const overlayPath of CITATION_OVERLAY_PATHS) {
    const overlay = readJson(overlayPath);
    assert(overlay.schema === OVERLAY_SCHEMA, `Expected ${OVERLAY_SCHEMA}; got ${overlay.schema}`);
    assert(overlay.scope?.nodeCount === candidateIds.size, "Citation overlay candidate scope is stale");
    assert(overlay.scope?.baseUnionEdges === unionEdgeCount, "Citation overlay base-union count is stale");
    assert(overlay.scope?.overlayEdges === overlay.edges?.length, "Citation overlay edge count is stale");
    assert(overlay.scope?.expectedUnionEdges === unionEdgeCount + overlay.edges.length, "Citation overlay union count is stale");
    assert(typeof overlay.edgeProvenance === "string" && overlay.edgeProvenance, "Citation overlay requires edge provenance");
    const overlayKeys = new Set();
    const edges = overlay.edges.map((pair) => {
      assert(Array.isArray(pair) && pair.length === 2, "Citation overlay edges must be [source, target]");
      const [source, target] = pair;
      assert(candidateIds.has(source) && candidateIds.has(target), `Citation overlay endpoint is outside the candidate scope: ${source} -> ${target}`);
      assert(source !== target, `Citation overlay contains self-link ${source}`);
      const key = `${source}\u0000${target}`;
      assert(!existingKeys.has(key), `Citation overlay duplicates an earlier edge ${source} -> ${target}`);
      assert(!overlayKeys.has(key), `Citation overlay contains duplicate edge ${source} -> ${target}`);
      overlayKeys.add(key);
      return { source, target, provenance: overlay.edgeProvenance };
    });
    for (const key of overlayKeys) existingKeys.add(key);
    unionEdgeCount += edges.length;
    overlays.push({
      overlay,
      sourceEdges: edges,
      edges: edges.filter((edge) => networkIds.has(edge.source) && networkIds.has(edge.target)),
    });
  }
  return {
    overlays,
    edges: overlays.flatMap((entry) => entry.edges),
  };
}

function buildAsset(snapshot) {
  assert(snapshot.schema === SOURCE_SCHEMA, `Expected ${SOURCE_SCHEMA}; got ${snapshot.schema}`);
  const sourceNodes = [...snapshot.nodes].sort((left, right) => left.id.localeCompare(right.id));
  const sourceEdges = [...snapshot.edges].sort((left, right) => left.source.localeCompare(right.source)
    || left.target.localeCompare(right.target)
    || left.provenance.localeCompare(right.provenance));
  const audits = loadToolkitAudits();
  const joinedSourceNodes = sourceNodes.map((node) => ({
    ...node,
    toolkit: toolkitForNode(node, audits),
  }));
  const candidateNodes = joinedSourceNodes
    .filter(isCandidateNetworkPublication)
    .map((node) => ({
      ...node,
      scope: scopeForNode(node),
  }));
  const verifiedDoiNodes = candidateNodes.filter(hasVerifiedDoiUrl);
  const networkNodes = candidateNodes.filter(isNetworkPublication);
  const candidateIds = new Set(candidateNodes.map((node) => node.id));
  const networkIds = new Set(networkNodes.map((node) => node.id));
  const candidateSnapshotEdges = sourceEdges.filter((edge) =>
    candidateIds.has(edge.source) && candidateIds.has(edge.target));
  const snapshotNetworkEdges = sourceEdges.filter((edge) =>
    networkIds.has(edge.source) && networkIds.has(edge.target));
  const citationOverlays = loadCitationOverlays(
    candidateIds,
    networkIds,
    candidateSnapshotEdges,
  );
  const doiResolutionScope = citationOverlays.overlays
    .map((entry) => entry.overlay.scope)
    .find((scope) => Number.isInteger(scope?.resolvedDoiNodes));
  assert(doiResolutionScope?.doiBearingNodes === verifiedDoiNodes.length,
    "Exact-DOI overlay bearing-node count is stale");
  assert(doiResolutionScope?.resolvedDoiNodes === verifiedDoiNodes.length,
    "Every canonical DOI node must be resolver-verified");
  const networkEdges = [...snapshotNetworkEdges, ...citationOverlays.edges]
    .sort((left, right) => left.source.localeCompare(right.source)
      || left.target.localeCompare(right.target)
      || left.provenance.localeCompare(right.provenance));
  const layouts = createNetworkLayouts(networkNodes, networkEdges);
  const nodeIndex = new Map(networkNodes.map((node, index) => [node.id, index]));

  const assetNodes = networkNodes.map((node, index) => ({
    ...node,
    eligibility: {
      verifiedDoiUrl: true,
      citationMetadataAvailable: true,
      citationMetadataProviders: citationMetadataProviders(node),
    },
    network: {
      inDegree: layouts.metrics.incomingDegree[index],
      outDegree: layouts.metrics.outgoingDegree[index],
      weakDegree: layouts.metrics.weakDegree[index],
      pageRank: Number(layouts.metrics.pageRank[index].toFixed(12)),
      component: layouts.metrics.component[index],
      isolated: layouts.metrics.weakDegree[index] === 0,
      prominence: Number(layouts.metrics.prominence[index].toFixed(9)),
      radius: Number(layouts.metrics.radii[index].toFixed(6)),
    },
    layouts: {
      topology: layouts.topology[index],
      timeline: layouts.timeline[index],
    },
  }));
  const assetEdges = networkEdges.map((edge) => [
    nodeIndex.get(edge.source),
    nodeIndex.get(edge.target),
    edge.provenance,
  ]);

  const sourceCounts = {
    nodes: joinedSourceNodes.length,
    edges: sourceEdges.length,
    audiotactileConfirmed: joinedSourceNodes.filter((node) => node.modality.audiotactile.verified).length,
    toolkitRecordJoins: joinedSourceNodes.reduce((total, node) => total + node.toolkit.records.length, 0),
    toolkitNodeJoins: joinedSourceNodes.filter((node) => node.toolkit.records.length).length,
  };
  const counts = {
    nodes: assetNodes.length,
    edges: assetEdges.length,
    audiotactileConfirmed: assetNodes.filter((node) => node.modality.audiotactile.verified).length,
    laterAuditAdditions: assetNodes.filter((node) =>
      node.scope.provenance === "later_exact_doi_audit").length,
    toolkitRecordJoins: assetNodes.reduce((total, node) => total + node.toolkit.records.length, 0),
    toolkitInScopeRecordJoins: assetNodes.reduce((total, node) =>
      total + node.toolkit.records.filter(isInScopeToolkitRecord).length, 0),
    toolkitNodeJoins: assetNodes.filter((node) => node.toolkit.records.length).length,
    toolkitInScopeNodeJoins: assetNodes.filter((node) =>
      node.toolkit.records.some(isInScopeToolkitRecord)).length,
    toolkitRunnableNodes: assetNodes.filter((node) => node.toolkit.status === "runnable").length,
    toolkitRunnableRecords: assetNodes.reduce((total, node) =>
      total + node.toolkit.records.filter((record) =>
        isInScopeToolkitRecord(record) && record.recreatable).length, 0),
    toolkitSupportedIncompleteNodes: assetNodes.filter((node) =>
      node.toolkit.status === "supported_incomplete").length,
    toolkitNotAssessedNodes: assetNodes.filter((node) =>
      node.toolkit.status === "not_assessed").length,
    toolkitAdjacentConflictNodes: assetNodes.filter((node) =>
      node.toolkit.status === "adjacent_scope_conflict").length,
    toolkitManualReviewRecords: assetNodes.reduce((total, node) =>
      total + node.toolkit.records.filter((record) => record.manualReview).length, 0),
    toolkitManualReviewNodes: assetNodes.filter((node) =>
      node.toolkit.records.some((record) => record.manualReview)).length,
    connectedNodes: assetNodes.filter((node) => !node.network.isolated).length,
    isolatedNodes: assetNodes.filter((node) => node.network.isolated).length,
    weakComponents: layouts.metrics.components.length,
    abstractsAvailable: assetNodes.filter((node) => node.abstract.status === "available").length,
    abstractsSourceLinkOnly: assetNodes.filter((node) => node.abstract.status === "source_link_only").length,
    abstractsNotAvailable: assetNodes.filter((node) => node.abstract.status === "not_available").length,
  };

  return {
    schema: ASSET_SCHEMA,
    generatedOn: citationOverlays.overlays
      .map((entry) => entry.overlay.capturedOn)
      .sort()
      .at(-1),
    generatorVersion: GENERATOR_VERSION,
    sourceSnapshot: {
      id: snapshot.snapshotId,
      builtOn: snapshot.builtOn,
      scopeClaim: snapshot.scopeClaim,
    },
    citationOverlays: citationOverlays.overlays.map(({ overlay, sourceEdges: overlaySourceEdges, edges }) => ({
      id: overlay.overlayId,
      capturedOn: overlay.capturedOn,
      provider: overlay.provider.name,
      edgeProvenance: overlay.edgeProvenance,
      sourceEdges: overlaySourceEdges.length,
      addedEdges: edges.length,
      scope: overlay.scope,
    })),
    sourceCounts,
    selectionAudit: {
      candidatePublications: candidateNodes.length,
      withVerifiedDoiUrl: verifiedDoiNodes.length,
      doiResolverVerified: doiResolutionScope.resolvedDoiNodes,
      withCitationMetadata: networkNodes.length,
      excludedMissingVerifiedDoiUrl: candidateNodes.length - verifiedDoiNodes.length,
      excludedMissingCitationMetadata: verifiedDoiNodes.length - networkNodes.length,
    },
    methodology: {
      edgeDirection: snapshot.sourceMethodology.edgeDirection,
      edgeCoverage: "Every directed citation captured between eligible displayed publications is retained from the frozen multi-source snapshot, the dated exact-DOI OpenAlex overlay, and the primary-source reference-list audit of provider-isolated records. Missing lines can still reflect provider coverage, reference-resolution gaps, or unavailable reference lists.",
      selection: "Starts with every non-review publication manually confirmed as audiotactile in the legacy citation audit, plus non-review publications added by an exact-DOI Toolkit literature audit with at least one non-adjacent audiotactile PPS task record. A paper is displayed only when its normalized DOI, DOI-keyed source identity, and canonical https://doi.org URL agree, the dated exact-DOI resolver audit confirms every DOI-bearing candidate, and at least one identified metadata provider supplies a finite citation count, including a valid count of zero. Toolkit readiness is an encoding, never an inclusion gate.",
      scopeProvenance: {
        legacyConfirmed: "Manually confirmed audiotactile in the legacy citation-corpus audit.",
        laterExactDoiAudit: "Added by an exact normalized DOI join to a non-adjacent Toolkit literature record.",
      },
      centrality: {
        pageRank: "Retained from the directed 1,712-publication source corpus.",
        betweennessApprox: "Retained approximate betweenness from the 1,712-publication source corpus.",
        influence: "Retained source-corpus navigation score; it is not a quality score.",
        inducedPageRank: "Recomputed deterministically over the displayed 94-publication directed citation graph with damping 0.85 and 100 fixed iterations.",
        prominence: "Layout-only score: 55% normalized log source-corpus citations received, 30% displayed-network PageRank, and 15% normalized log displayed-network indegree. It is not a study-quality score.",
      },
      sizing: {
        metric: "Displayed-network citation indegree.",
        encoding: "Circle area (radius squared) is linear in normalized log1p displayed-network indegree between the declared minimum and maximum radii.",
      },
      layouts: {
        topology: "Deterministic continuous density-preserving force layout. Citation neighbours attract, every paper repels every other paper, all nodes share one weak centering force, and radius-aware collision separation keeps each publication distinct. No node class is assigned to a perimeter.",
        timeline: "Deterministic continuous year-anchored layout. Horizontal position follows publication year (unknown years last), citation topology softly informs vertical position, and radius-aware collision separation remains active.",
      },
      abstracts: snapshot.sourceMethodology.abstractPolicy,
      toolkitJoin: "All Toolkit literature records and manual parameter reviews are attached by normalized DOI only; fuzzy title/author matching is not used. Runnable, supported-incomplete, not-assessed, and adjacent/scope-conflict are display states, not corpus filters.",
    },
    counts,
    layoutBounds: {
      square: {
        minX: 0,
        maxX: 1,
        minY: 0,
        maxY: 1,
        nodeExtentMargin: LAYOUT_MARGIN,
        minimumNodeRadius: NODE_RADIUS_MIN,
        maximumNodeRadius: NODE_RADIUS_MAX,
        requiredNodeClearance: NODE_CLEARANCE,
      },
      topology: {
        algorithm: "deterministic continuous density-preserving citation force layout",
        iterations: TOPOLOGY_ITERATIONS,
        weakCitationSprings: layouts.metrics.weakEdges.length,
        principalComponentNodes: layouts.metrics.components[0].length,
        ...layouts.quality.topology,
      },
      timeline: {
        algorithm: "deterministic continuous year-anchored citation layout",
        iterations: Math.floor(TOPOLOGY_ITERATIONS / 2),
        nodeOrder: ["year on horizontal axis", "unknown year last", "stable ID jitter"],
        minYear: layouts.minYear,
        maxYear: layouts.maxYear,
        ...layouts.quality.timeline,
      },
    },
    facets: {
      corpusTiers: countValues(assetNodes.map((node) => node.corpus.tier)),
      themes: countValues(assetNodes.map((node) => node.corpus.theme)),
      documentRoles: countValues(assetNodes.map((node) => node.corpus.documentRole)),
      years: countValues(assetNodes.map((node) => node.year ?? "unknown")),
      toolkitStatuses: countValues(assetNodes.map((node) => node.toolkit.status)),
      scopeProvenance: countValues(assetNodes.map((node) => node.scope.provenance)),
      edgeProvenance: countValues(networkEdges.map((edge) => edge.provenance)),
    },
    nodes: assetNodes,
    edges: assetEdges,
  };
}

function validateSnapshot(snapshot) {
  assert(snapshot.schema === SOURCE_SCHEMA, `Unexpected source schema: ${snapshot.schema}`);
  assert(snapshot.nodes.length === SOURCE_EXPECTED.nodes, `Expected ${SOURCE_EXPECTED.nodes} source nodes; got ${snapshot.nodes.length}`);
  assert(snapshot.edges.length === SOURCE_EXPECTED.edges, `Expected ${SOURCE_EXPECTED.edges} source edges; got ${snapshot.edges.length}`);
  const ids = snapshot.nodes.map((node) => node.id);
  assert(new Set(ids).size === ids.length, "Source node IDs must be unique");
  assert(ids.every((id, index) => index === 0 || ids[index - 1].localeCompare(id) <= 0), "Source nodes must be sorted by ID");
  const idSet = new Set(ids);
  assert(snapshot.edges.every((edge) => idSet.has(edge.source) && idSet.has(edge.target)), "Every source edge endpoint must resolve");
  assert(
    snapshot.nodes.filter((node) => node.modality.audiotactile.verified).length === SOURCE_EXPECTED.audiotactileConfirmed,
    `Expected ${SOURCE_EXPECTED.audiotactileConfirmed} verified audiotactile source nodes`,
  );
  assert(snapshot.nodes.every((node) => !node.modality.visuotactile.verified), "No visuotactile node may be marked verified without a manual audit");
  const abstractStatuses = new Set(["available", "source_link_only", "not_available"]);
  assert(snapshot.nodes.every((node) => abstractStatuses.has(node.abstract.status)), "Unexpected abstract status");
  assert(snapshot.nodes.every((node) => node.abstract.status !== "available" || (node.abstract.text && node.abstract.source === "OpenAlex" && node.abstract.license === "CC0-1.0")), "Published abstract text must have OpenAlex CC0 provenance");
}

function validateAsset(asset) {
  assert(asset.schema === ASSET_SCHEMA, `Unexpected asset schema: ${asset.schema}`);
  for (const [name, expected] of Object.entries(SOURCE_EXPECTED)) {
    assert(asset.sourceCounts[name] === expected, `Expected sourceCounts.${name}=${expected}; got ${asset.sourceCounts[name]}`);
  }
  for (const [name, expected] of Object.entries(NETWORK_EXPECTED)) {
    assert(asset.counts[name] === expected, `Expected counts.${name}=${expected}; got ${asset.counts[name]}`);
  }
  assert(asset.nodes.length === NETWORK_EXPECTED.nodes, "Network node array length does not match counts");
  assert(asset.edges.length === NETWORK_EXPECTED.edges, "Network edge array length does not match counts");
  const ids = asset.nodes.map((node) => node.id);
  assert(new Set(ids).size === ids.length, "Network publication IDs must be unique");
  assert(ids.every((id, index) => index === 0 || ids[index - 1].localeCompare(id) <= 0), "Network publication nodes must remain ID-sorted");
  assert(asset.nodes.every((node) => node.corpus.documentRole !== "review"), "Review publications must not enter the audiotactile study network");
  assert(asset.nodes.every(hasVerifiedDoiUrl), "Every network publication requires a verified canonical DOI URL");
  assert(asset.nodes.every(hasCitationMetadata), "Every network publication requires provider-backed citation metadata");
  assert(asset.nodes.every((node) => node.eligibility?.verifiedDoiUrl
    && node.eligibility?.citationMetadataAvailable
    && node.eligibility?.citationMetadataProviders?.length), "Network eligibility metadata is stale");
  assert(asset.selectionAudit?.candidatePublications === 97, "Candidate publication count is stale");
  assert(asset.selectionAudit?.withVerifiedDoiUrl === NETWORK_EXPECTED.nodes, "Verified DOI selection count is stale");
  assert(asset.selectionAudit?.doiResolverVerified === NETWORK_EXPECTED.nodes, "DOI resolver-verification count is stale");
  assert(asset.selectionAudit?.withCitationMetadata === NETWORK_EXPECTED.nodes, "Citation-metadata selection count is stale");
  assert(asset.selectionAudit?.excludedMissingVerifiedDoiUrl === 3, "Missing-DOI exclusion count is stale");
  assert(asset.selectionAudit?.excludedMissingCitationMetadata === 0, "Missing-citation-metadata exclusion count is stale");
  assert(asset.nodes.every((node) => node.modality.audiotactile.verified
    || (node.scope.provenance === "later_exact_doi_audit"
      && node.toolkit.records.some(isInScopeToolkitRecord))), "Every network node needs legacy confirmation or a later exact-DOI in-scope audit basis");
  assert(asset.nodes.filter((node) => node.scope.provenance === "legacy_confirmed").length
    === NETWORK_EXPECTED.audiotactileConfirmed, "Legacy scope provenance count is stale");
  assert(asset.nodes.filter((node) => node.scope.provenance === "later_exact_doi_audit").length
    === NETWORK_EXPECTED.laterAuditAdditions, "Later exact-DOI scope provenance count is stale");
  const validToolkitStatuses = new Set([
    "runnable",
    "supported_incomplete",
    "not_assessed",
    "adjacent_scope_conflict",
  ]);
  assert(asset.nodes.every((node) => validToolkitStatuses.has(node.toolkit.status)), "Unexpected Toolkit status");
  for (const node of asset.nodes) {
    const inScopeRecords = node.toolkit.records.filter(isInScopeToolkitRecord);
    assert(node.toolkit.inScopeRecordCount === inScopeRecords.length, `Stale in-scope record count on ${node.id}`);
    assert(node.toolkit.records.every((record) => record.inScope === isInScopeToolkitRecord(record)), `Stale record scope flag on ${node.id}`);
    const expectedStatus = inScopeRecords.some((record) => record.recreatable)
      ? "runnable"
      : inScopeRecords.length
        ? "supported_incomplete"
        : node.toolkit.records.length
          ? "adjacent_scope_conflict"
          : "not_assessed";
    assert(node.toolkit.status === expectedStatus, `Toolkit status is stale on ${node.id}`);
  }

  const edgeKeys = new Set();
  const incomingDegree = Array(asset.nodes.length).fill(0);
  const outgoingDegree = Array(asset.nodes.length).fill(0);
  const weakEdgeKeys = new Set();
  for (const edge of asset.edges) {
    assert(Array.isArray(edge) && edge.length === 3, "Every network edge must be [source, target, provenance]");
    const [source, target, provenance] = edge;
    assert(Number.isInteger(source) && source >= 0 && source < asset.nodes.length, "Network edge source must resolve");
    assert(Number.isInteger(target) && target >= 0 && target < asset.nodes.length, "Network edge target must resolve");
    assert(source !== target, "Network citation edges must not be self-links");
    assert(typeof provenance === "string" && provenance, "Network citation edges require provenance");
    const key = `${source}:${target}`;
    assert(!edgeKeys.has(key), `Duplicate network citation edge ${key}`);
    edgeKeys.add(key);
    incomingDegree[target] += 1;
    outgoingDegree[source] += 1;
    weakEdgeKeys.add(source < target ? `${source}:${target}` : `${target}:${source}`);
  }
  assert(weakEdgeKeys.size === 747, `Expected 747 weak citation links; got ${weakEdgeKeys.size}`);
  assert(asset.nodes.every((node, index) => node.network.inDegree === incomingDegree[index]
    && node.network.outDegree === outgoingDegree[index]), "Displayed-network directed degrees are stale");
  const normalizedIncoming = normalizedValues(incomingDegree, true);
  const minimumArea = NODE_RADIUS_MIN ** 2;
  const areaRange = NODE_RADIUS_MAX ** 2 - minimumArea;
  for (let index = 0; index < asset.nodes.length; index += 1) {
    const expectedRadius = Math.sqrt(minimumArea + areaRange * normalizedIncoming[index]);
    assert(Math.abs(asset.nodes[index].network.radius - expectedRadius) < 1.1e-6, `Citation-area radius is stale on ${asset.nodes[index].id}`);
    for (let other = 0; other < asset.nodes.length; other += 1) {
      if (incomingDegree[index] > incomingDegree[other]) {
        assert(asset.nodes[index].network.radius >= asset.nodes[other].network.radius, "Node radius must be monotonic in displayed-network indegree");
      }
    }
  }
  assert(Math.abs(asset.nodes.reduce((total, node) => total + node.network.pageRank, 0) - 1) < 1e-8, "Displayed-network PageRank must sum to one");

  const square = asset.layoutBounds.square;
  assert(square.nodeExtentMargin === LAYOUT_MARGIN
    && square.minimumNodeRadius === NODE_RADIUS_MIN
    && square.maximumNodeRadius === NODE_RADIUS_MAX
    && square.requiredNodeClearance === NODE_CLEARANCE, "Square layout bounds metadata is stale");
  for (const layoutName of ["topology", "timeline"]) {
    const positions = asset.nodes.map((node) => node.layouts[layoutName]);
    assert(positions.every((position) => position
      && Number.isFinite(position.x) && Number.isFinite(position.y)
      && position.x >= 0 && position.x <= 1
      && position.y >= 0 && position.y <= 1), `All ${layoutName} coordinates must be finite and inside the normalized square bounds`);
    const coordinateKeys = positions.map((position) => `${position.x.toFixed(6)}:${position.y.toFixed(6)}`);
    assert(new Set(coordinateKeys).size === asset.nodes.length, `${layoutName} must assign one unique continuous coordinate to every publication`);
    for (let index = 0; index < positions.length; index += 1) {
      const radius = asset.nodes[index].network.radius;
      assert(positions[index].x - radius >= LAYOUT_MARGIN - 0.000002
        && positions[index].x + radius <= 1 - LAYOUT_MARGIN + 0.000002
        && positions[index].y - radius >= LAYOUT_MARGIN - 0.000002
        && positions[index].y + radius <= 1 - LAYOUT_MARGIN + 0.000002, `${layoutName} node extents violate the square margin`);
      for (let other = index + 1; other < positions.length; other += 1) {
        const distance = Math.hypot(
          positions[index].x - positions[other].x,
          positions[index].y - positions[other].y,
        );
        const required = radius + asset.nodes[other].network.radius + NODE_CLEARANCE;
        assert(distance >= required - 0.000003, `${layoutName} publications overlap or violate the declared clearance`);
      }
    }
    assert(asset.layoutBounds[layoutName].clearanceViolations === 0, `${layoutName} quality metadata reports a collision`);
  }
  assert(asset.layoutBounds.topology.edgeToPrincipalNonNeighbourRatio < 0.75, "Topology layout must place citation neighbours materially closer than principal-component non-neighbours");
  assert(asset.layoutBounds.topology.principalComponentSpanX >= 0.7
    && asset.layoutBounds.topology.principalComponentSpanY >= 0.7, "Topology principal component must use the available map area");
  assert(asset.layoutBounds.topology.principalComponentOccupiedGridCells6x6 >= 20, "Topology density must occupy a broad set of map regions");
  assert(asset.layoutBounds.topology.medianNearestNeighbourDistance >= 0.055, "Topology papers must remain visually separated");
  assert(asset.layoutBounds.topology.isolatedNodesNearBoundary <= 3, "Topology must not force isolates onto a perimeter");
  assert(asset.layoutBounds.topology.uniqueRoundedX >= 85
    && asset.layoutBounds.topology.uniqueRoundedY >= 85, "Topology coordinates must remain continuous rather than grid-snapped");
  const knownTimeline = asset.nodes
    .map((node) => ({ year: node.year, x: node.layouts.timeline.x }))
    .filter((entry) => Number.isInteger(entry.year));
  assert(spearman(knownTimeline.map((entry) => entry.year), knownTimeline.map((entry) => entry.x)) > 0.9, "Timeline horizontal coordinates must preserve chronological order");
}

function report(asset, output, snapshotOutput, wrote) {
  const result = {
    schema: asset.schema,
    wrote,
    output: path.relative(REPO_ROOT, output),
    snapshotOutput: snapshotOutput ? path.relative(REPO_ROOT, snapshotOutput) : null,
    sourceCounts: asset.sourceCounts,
    counts: asset.counts,
  };
  if (wrote && fs.existsSync(output)) result.outputBytes = fs.statSync(output).size;
  if (wrote && snapshotOutput && fs.existsSync(snapshotOutput)) {
    result.snapshotBytes = fs.statSync(snapshotOutput).size;
  }
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  let snapshot;
  if (options.sourceBundle) {
    snapshot = createSourceSnapshot(options.sourceBundle);
    validateSnapshot(snapshot);
    if (!options.validateOnly) writeJson(options.snapshotOutput, snapshot, true);
  } else {
    snapshot = readJson(options.sourceSnapshot);
    validateSnapshot(snapshot);
  }

  const asset = buildAsset(snapshot);
  validateAsset(asset);
  if (!options.validateOnly) writeJson(options.output, asset, options.pretty);
  report(asset, options.output, options.snapshotOutput, !options.validateOnly);
}

try {
  main();
} catch (error) {
  process.stderr.write(`Publication-network build failed: ${error.message || error}\n`);
  process.exitCode = 1;
}
