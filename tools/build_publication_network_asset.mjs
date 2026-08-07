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
  "src/peripersonal_space_toolkit/dashboard/publication_network.v1.json",
);
const COVERAGE_PATH = path.join(
  REPO_ROOT,
  "assets/preloads/audiotactile_literature_coverage.json",
);
const MANUAL_REVIEW_DIR = path.join(
  REPO_ROOT,
  "For-AI/audiotactile-paper-metadata-audit/manual_reviews",
);

const EXPECTED = Object.freeze({
  nodes: 1712,
  edges: 10109,
  audiotactileConfirmed: 101,
  toolkitRecordJoins: 73,
  toolkitNodeJoins: 69,
  toolkitManualReviewRecords: 24,
  toolkitManualReviewNodes: 21,
});

const SOURCE_SCHEMA = "pps-publication-citation-source.v1";
const ASSET_SCHEMA = "pps-publication-citation-network.v1";
const SNAPSHOT_ID = "pps-citation-network-20260807";
const SNAPSHOT_DATE = "2026-08-07";
const GENERATOR_VERSION = "1.1.0";

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

function createTimelineLayout(nodes) {
  const themes = [...new Set(nodes.map((node) => node.corpus.theme))].sort();
  const themeIndex = new Map(themes.map((theme, index) => [theme, index]));
  const years = nodes.map((node) => node.year).filter(Number.isInteger);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const span = Math.max(1, maxYear - minYear);
  const positions = new Map();
  for (const node of nodes) {
    const x = Number.isInteger(node.year)
      ? 0.04 + ((node.year - minYear) / span) * 0.92
      : 0.015;
    const band = themeIndex.get(node.corpus.theme) || 0;
    const jitter = (hashUnit(`${node.id}:timeline-y`) - 0.5) * Math.min(0.055, 0.62 / themes.length);
    const y = (band + 0.5) / themes.length + jitter;
    positions.set(node.id, { x: roundCoordinate(x), y: roundCoordinate(y) });
  }
  return { positions, themes, minYear, maxYear };
}

function createStructuralLayout(nodes, edges, { connectedTargetRadius = null } = {}) {
  const indexById = new Map(nodes.map((node, index) => [node.id, index]));
  const degrees = new Uint32Array(nodes.length);
  const indexedEdges = [];
  for (const edge of edges) {
    const source = indexById.get(edge.source);
    const target = indexById.get(edge.target);
    if (source === undefined || target === undefined || source === target) continue;
    indexedEdges.push([source, target]);
    degrees[source] += 1;
    degrees[target] += 1;
  }

  const active = nodes.map((_, index) => index).filter((index) => degrees[index] > 0);
  const isolated = nodes.map((_, index) => index).filter((index) => degrees[index] === 0);
  const activeSet = new Set(active);
  const x = new Float64Array(nodes.length);
  const y = new Float64Array(nodes.length);
  const themes = [...new Set(nodes.map((node) => node.corpus.theme))].sort();
  const themeIndex = new Map(themes.map((theme, index) => [theme, index]));

  for (const index of active) {
    const node = nodes[index];
    const sector = (themeIndex.get(node.corpus.theme) || 0) / Math.max(1, themes.length);
    const angle = (sector + (hashUnit(`${node.id}:structure-angle`) - 0.5) * 0.075) * Math.PI * 2;
    const desiredRadius = 0.07 + 0.32 * (1 - Math.sqrt(Math.max(0, node.centrality.influence)));
    const radius = desiredRadius * (0.78 + 0.44 * hashUnit(`${node.id}:structure-radius`));
    x[index] = Math.cos(angle) * radius;
    y[index] = Math.sin(angle) * radius;
  }

  // Deterministic centrality-aware force simulation. Attraction follows citation
  // links; a local repulsion grid keeps dense areas legible; influence pulls
  // highly central publications toward the structural overview's centre.
  const iterations = 260;
  const fx = new Float64Array(nodes.length);
  const fy = new Float64Array(nodes.length);
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    fx.fill(0);
    fy.fill(0);

    for (const [source, target] of indexedEdges) {
      if (!activeSet.has(source) || !activeSet.has(target)) continue;
      let dx = x[target] - x[source];
      let dy = y[target] - y[source];
      let distance = Math.hypot(dx, dy);
      if (distance < 1e-7) {
        const angle = hashUnit(`${nodes[source].id}:${nodes[target].id}`) * Math.PI * 2;
        dx = Math.cos(angle) * 1e-4;
        dy = Math.sin(angle) * 1e-4;
        distance = 1e-4;
      }
      const desired = 0.018 + 0.018 / Math.sqrt(1 + Math.min(degrees[source], degrees[target]));
      const strength = (distance - desired) * 0.0055;
      const ux = dx / distance;
      const uy = dy / distance;
      fx[source] += ux * strength;
      fy[source] += uy * strength;
      fx[target] -= ux * strength;
      fy[target] -= uy * strength;
    }

    const cellSize = 0.032;
    const grid = new Map();
    for (const index of active) {
      const gx = Math.floor(x[index] / cellSize);
      const gy = Math.floor(y[index] / cellSize);
      const key = `${gx}:${gy}`;
      const bucket = grid.get(key) || [];
      bucket.push(index);
      grid.set(key, bucket);
    }
    for (const index of active) {
      const gx = Math.floor(x[index] / cellSize);
      const gy = Math.floor(y[index] / cellSize);
      for (let ox = -1; ox <= 1; ox += 1) {
        for (let oy = -1; oy <= 1; oy += 1) {
          for (const other of grid.get(`${gx + ox}:${gy + oy}`) || []) {
            if (other <= index) continue;
            let dx = x[other] - x[index];
            let dy = y[other] - y[index];
            let distance = Math.hypot(dx, dy);
            if (distance < 1e-7) {
              const angle = hashUnit(`${nodes[index].id}|${nodes[other].id}`) * Math.PI * 2;
              dx = Math.cos(angle) * 1e-4;
              dy = Math.sin(angle) * 1e-4;
              distance = 1e-4;
            }
            const minimum = 0.012 + 0.002 * Math.log1p(degrees[index] + degrees[other]);
            if (distance >= minimum) continue;
            const push = (minimum - distance) * 0.065;
            const ux = dx / distance;
            const uy = dy / distance;
            fx[index] -= ux * push;
            fy[index] -= uy * push;
            fx[other] += ux * push;
            fy[other] += uy * push;
          }
        }
      }
    }

    for (const index of active) {
      const node = nodes[index];
      const radius = Math.max(1e-7, Math.hypot(x[index], y[index]));
      const desiredRadius = 0.055 + 0.31 * (1 - Math.sqrt(Math.max(0, node.centrality.influence)));
      const radialForce = (desiredRadius - radius) * 0.008;
      fx[index] += (x[index] / radius) * radialForce;
      fy[index] += (y[index] / radius) * radialForce;

      const sector = (themeIndex.get(node.corpus.theme) || 0) / Math.max(1, themes.length);
      const angle = sector * Math.PI * 2;
      const communityRadius = 0.17 + 0.08 * (1 - node.centrality.influence);
      fx[index] += (Math.cos(angle) * communityRadius - x[index]) * 0.00016;
      fy[index] += (Math.sin(angle) * communityRadius - y[index]) * 0.00016;
    }

    const temperature = 0.014 * (1 - iteration / iterations) + 0.0012;
    for (const index of active) {
      const magnitude = Math.hypot(fx[index], fy[index]);
      const scale = magnitude > temperature ? temperature / magnitude : 1;
      x[index] = Math.max(-0.39, Math.min(0.39, x[index] + fx[index] * scale));
      y[index] = Math.max(-0.39, Math.min(0.39, y[index] + fy[index] * scale));
    }
  }

  const positions = new Map();
  for (const index of active) {
    positions.set(nodes[index].id, {
      x: roundCoordinate(0.5 + x[index]),
      y: roundCoordinate(0.5 + y[index]),
    });
  }

  if (Number.isFinite(connectedTargetRadius) && connectedTargetRadius > 0 && active.length) {
    const activePositions = active.map((index) => positions.get(nodes[index].id));
    const centroidX = activePositions.reduce((total, position) => total + position.x, 0) / activePositions.length;
    const centroidY = activePositions.reduce((total, position) => total + position.y, 0) / activePositions.length;
    const maximumRadius = activePositions.reduce((maximum, position) => Math.max(
      maximum,
      Math.hypot(position.x - centroidX, position.y - centroidY),
    ), 0);
    const scale = maximumRadius > 0 ? connectedTargetRadius / maximumRadius : 1;
    for (const index of active) {
      const position = positions.get(nodes[index].id);
      positions.set(nodes[index].id, {
        x: roundCoordinate(0.5 + (position.x - centroidX) * scale),
        y: roundCoordinate(0.5 + (position.y - centroidY) * scale),
      });
    }
  }

  const sortedIsolated = [...isolated].sort((left, right) => {
    const leftNode = nodes[left];
    const rightNode = nodes[right];
    return leftNode.corpus.theme.localeCompare(rightNode.corpus.theme)
      || (leftNode.year || 9999) - (rightNode.year || 9999)
      || leftNode.id.localeCompare(rightNode.id);
  });
  const ringCount = Math.max(1, Math.ceil(sortedIsolated.length / 72));
  sortedIsolated.forEach((index, order) => {
    const ring = order % ringCount;
    const slot = Math.floor(order / ringCount);
    const slots = Math.ceil((sortedIsolated.length - ring) / ringCount);
    const radius = 0.425 + (ring / Math.max(1, ringCount - 1)) * 0.062;
    const angle = (slot / Math.max(1, slots) + hashUnit(`${nodes[index].id}:isolated`) * 0.0025) * Math.PI * 2;
    positions.set(nodes[index].id, {
      x: roundCoordinate(0.5 + Math.cos(angle) * radius),
      y: roundCoordinate(0.5 + Math.sin(angle) * radius),
    });
  });

  return {
    positions,
    algorithm: "deterministic centrality-aware citation-force layout with isolated-node rings",
    connectedNodeCount: active.length,
    isolatedNodeCount: isolated.length,
    iterations,
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
      records: [],
    };
  }
  const joinedRecords = records.map((record) => {
    const review = audits.reviewsByRecordId.get(record.record_id);
    return {
      recordId: record.record_id,
      citationShort: record.citation_short || "",
      coverageCategory: record.coverage_category || "",
      taskFamily: record.audiotactile_task_family || "",
      recreatable: Boolean(record.can_recreate_audiotactile_components_now),
      templateIds: [...(record.current_template_ids || [])],
      missingParameters: [...(record.missing_publication_parameters || [])],
      manualReview: review ? compactManualReview(review) : null,
    };
  });
  return {
    joinStatus: joinedRecords.some((record) => record.manualReview)
      ? "doi_matched_manual_parameter_review"
      : "doi_matched_literature_audit",
    records: joinedRecords,
  };
}

function countValues(values) {
  const counts = {};
  for (const value of values) counts[value] = (counts[value] || 0) + 1;
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function buildAsset(snapshot) {
  assert(snapshot.schema === SOURCE_SCHEMA, `Expected ${SOURCE_SCHEMA}; got ${snapshot.schema}`);
  const nodes = [...snapshot.nodes].sort((left, right) => left.id.localeCompare(right.id));
  const edges = [...snapshot.edges].sort((left, right) => left.source.localeCompare(right.source)
    || left.target.localeCompare(right.target)
    || left.provenance.localeCompare(right.provenance));
  const timeline = createTimelineLayout(nodes);
  const structure = createStructuralLayout(nodes, edges);
  const audiotactileNodes = nodes.filter((node) => node.modality.audiotactile.verified);
  const audiotactileNodeIds = new Set(audiotactileNodes.map((node) => node.id));
  const audiotactileEdges = edges.filter((edge) =>
    audiotactileNodeIds.has(edge.source) && audiotactileNodeIds.has(edge.target));
  const audiotactileTimeline = createTimelineLayout(audiotactileNodes);
  const audiotactileStructure = createStructuralLayout(
    audiotactileNodes,
    audiotactileEdges,
    { connectedTargetRadius: 0.32 },
  );
  const audits = loadToolkitAudits();
  const nodeIndex = new Map(nodes.map((node, index) => [node.id, index]));

  const assetNodes = nodes.map((node) => ({
    ...node,
    layouts: {
      timeline: timeline.positions.get(node.id),
      structure: structure.positions.get(node.id),
      ...(node.modality.audiotactile.verified ? {
        audiotactileStructure: audiotactileStructure.positions.get(node.id),
        audiotactileTimeline: audiotactileTimeline.positions.get(node.id),
      } : {}),
    },
    toolkit: toolkitForNode(node, audits),
  }));
  const assetEdges = edges.map((edge) => [
    nodeIndex.get(edge.source),
    nodeIndex.get(edge.target),
    edge.provenance,
  ]);

  const counts = {
    nodes: assetNodes.length,
    edges: assetEdges.length,
    audiotactileConfirmed: assetNodes.filter((node) => node.modality.audiotactile.verified).length,
    visuotactileVerified: assetNodes.filter((node) => node.modality.visuotactile.verified).length,
    visuotactileProvisional: assetNodes.filter((node) => node.modality.visuotactile.status === "provisional_keyword_candidate").length,
    toolkitRecordJoins: assetNodes.reduce((total, node) => total + node.toolkit.records.length, 0),
    toolkitNodeJoins: assetNodes.filter((node) => node.toolkit.records.length).length,
    toolkitManualReviewRecords: assetNodes.reduce((total, node) =>
      total + node.toolkit.records.filter((record) => record.manualReview).length, 0),
    toolkitManualReviewNodes: assetNodes.filter((node) =>
      node.toolkit.records.some((record) => record.manualReview)).length,
    abstractsAvailable: assetNodes.filter((node) => node.abstract.status === "available").length,
    abstractsSourceLinkOnly: assetNodes.filter((node) => node.abstract.status === "source_link_only").length,
    abstractsNotAvailable: assetNodes.filter((node) => node.abstract.status === "not_available").length,
    isolatedNodes: structure.isolatedNodeCount,
  };

  return {
    schema: ASSET_SCHEMA,
    generatedOn: snapshot.builtOn,
    generatorVersion: GENERATOR_VERSION,
    sourceSnapshot: {
      id: snapshot.snapshotId,
      builtOn: snapshot.builtOn,
      scopeClaim: snapshot.scopeClaim,
    },
    methodology: {
      edgeDirection: snapshot.sourceMethodology.edgeDirection,
      centrality: {
        pageRank: "PageRank computed on directed within-corpus citations.",
        betweennessApprox: "Approximate betweenness centrality sampled over 80 source nodes.",
        influence: "Navigation score combining PageRank percentile (55%), indexed-citation percentile (30%), and approximate-betweenness percentile (15%); not a quality score.",
      },
      layouts: {
        timeline: "Publication year on x and corpus theme lane on y; unknown years occupy the far-left lane.",
        structure: `${structure.algorithm}; ${structure.iterations} fixed iterations. Positions aid navigation and are not Cartesian scientific measurements.`,
        audiotactileTimeline: `Verified audiotactile publications fitted to their ${audiotactileTimeline.minYear}-${audiotactileTimeline.maxYear} year range and corpus-theme lanes.`,
        audiotactileStructure: `${audiotactileStructure.algorithm} and connected-subgraph radius 0.32 on the verified audiotactile induced citation subgraph; ${audiotactileStructure.iterations} fixed iterations. Positions aid navigation and are not Cartesian scientific measurements.`,
      },
      modality: {
        audiotactile: snapshot.sourceMethodology.audiotactilePolicy,
        visuotactile: snapshot.sourceMethodology.visuotactilePolicy,
      },
      abstracts: snapshot.sourceMethodology.abstractPolicy,
      toolkitJoin: "Toolkit literature coverage and manual parameter reviews are joined by normalized DOI only; fuzzy title/author matching is not used.",
    },
    counts,
    layoutBounds: {
      timeline: {
        minYear: timeline.minYear,
        maxYear: timeline.maxYear,
        themes: timeline.themes,
      },
      structure: {
        connectedNodeCount: structure.connectedNodeCount,
        isolatedNodeCount: structure.isolatedNodeCount,
      },
      audiotactileTimeline: {
        minYear: audiotactileTimeline.minYear,
        maxYear: audiotactileTimeline.maxYear,
        themes: audiotactileTimeline.themes,
      },
      audiotactileStructure: {
        connectedNodeCount: audiotactileStructure.connectedNodeCount,
        isolatedNodeCount: audiotactileStructure.isolatedNodeCount,
      },
    },
    facets: {
      corpusTiers: countValues(assetNodes.map((node) => node.corpus.tier)),
      themes: countValues(assetNodes.map((node) => node.corpus.theme)),
      documentRoles: countValues(assetNodes.map((node) => node.corpus.documentRole)),
      years: countValues(assetNodes.map((node) => node.year ?? "unknown")),
      edgeProvenance: countValues(edges.map((edge) => edge.provenance)),
    },
    nodes: assetNodes,
    edges: assetEdges,
  };
}

function validateSnapshot(snapshot) {
  assert(snapshot.schema === SOURCE_SCHEMA, `Unexpected source schema: ${snapshot.schema}`);
  assert(snapshot.nodes.length === EXPECTED.nodes, `Expected ${EXPECTED.nodes} nodes; got ${snapshot.nodes.length}`);
  assert(snapshot.edges.length === EXPECTED.edges, `Expected ${EXPECTED.edges} edges; got ${snapshot.edges.length}`);
  const ids = snapshot.nodes.map((node) => node.id);
  assert(new Set(ids).size === ids.length, "Source node IDs must be unique");
  assert(ids.every((id, index) => index === 0 || ids[index - 1].localeCompare(id) <= 0), "Source nodes must be sorted by ID");
  const idSet = new Set(ids);
  assert(snapshot.edges.every((edge) => idSet.has(edge.source) && idSet.has(edge.target)), "Every source edge endpoint must resolve");
  assert(
    snapshot.nodes.filter((node) => node.modality.audiotactile.verified).length === EXPECTED.audiotactileConfirmed,
    `Expected ${EXPECTED.audiotactileConfirmed} verified audiotactile nodes`,
  );
  assert(snapshot.nodes.every((node) => !node.modality.visuotactile.verified), "No visuotactile node may be marked verified without a manual audit");
  const abstractStatuses = new Set(["available", "source_link_only", "not_available"]);
  assert(snapshot.nodes.every((node) => abstractStatuses.has(node.abstract.status)), "Unexpected abstract status");
  assert(snapshot.nodes.every((node) => node.abstract.status !== "available" || (node.abstract.text && node.abstract.source === "OpenAlex" && node.abstract.license === "CC0-1.0")), "Published abstract text must have OpenAlex CC0 provenance");
}

function validateAsset(asset) {
  assert(asset.schema === ASSET_SCHEMA, `Unexpected asset schema: ${asset.schema}`);
  assert(asset.counts.nodes === EXPECTED.nodes, `Expected ${EXPECTED.nodes} asset nodes`);
  assert(asset.counts.edges === EXPECTED.edges, `Expected ${EXPECTED.edges} asset edges`);
  assert(asset.counts.audiotactileConfirmed === EXPECTED.audiotactileConfirmed, `Expected ${EXPECTED.audiotactileConfirmed} verified audiotactile nodes`);
  assert(asset.counts.visuotactileVerified === 0, "No visuotactile nodes should be verified");
  assert(asset.counts.toolkitRecordJoins === EXPECTED.toolkitRecordJoins, `Expected ${EXPECTED.toolkitRecordJoins} toolkit record joins`);
  assert(asset.counts.toolkitNodeJoins === EXPECTED.toolkitNodeJoins, `Expected ${EXPECTED.toolkitNodeJoins} toolkit node joins`);
  assert(asset.counts.toolkitManualReviewRecords === EXPECTED.toolkitManualReviewRecords, `Expected ${EXPECTED.toolkitManualReviewRecords} manual-review record joins`);
  assert(asset.counts.toolkitManualReviewNodes === EXPECTED.toolkitManualReviewNodes, `Expected ${EXPECTED.toolkitManualReviewNodes} nodes with manual reviews`);
  assert(asset.edges.every((edge) => Number.isInteger(edge[0]) && edge[0] >= 0 && edge[0] < asset.nodes.length
    && Number.isInteger(edge[1]) && edge[1] >= 0 && edge[1] < asset.nodes.length), "Every indexed asset edge must resolve");
  assert(asset.nodes.every((node) => [node.layouts.timeline, node.layouts.structure].every((position) =>
    Number.isFinite(position.x) && Number.isFinite(position.y)
    && position.x >= 0 && position.x <= 1 && position.y >= 0 && position.y <= 1)), "All layout coordinates must be finite and normalized");
  const verifiedAudiotactile = asset.nodes.filter((node) => node.modality.audiotactile.verified);
  const otherNodes = asset.nodes.filter((node) => !node.modality.audiotactile.verified);
  assert(verifiedAudiotactile.every((node) => [
    node.layouts.audiotactileTimeline,
    node.layouts.audiotactileStructure,
  ].every((position) => Number.isFinite(position.x) && Number.isFinite(position.y)
    && position.x >= 0 && position.x <= 1 && position.y >= 0 && position.y <= 1)), "Verified audiotactile nodes require normalized subset-specific coordinates");
  assert(otherNodes.every((node) => node.layouts.audiotactileTimeline === undefined
    && node.layouts.audiotactileStructure === undefined), "Subset-specific coordinates must not be assigned outside the verified audiotactile set");
  assert(asset.layoutBounds.audiotactileTimeline.minYear === 2000
    && asset.layoutBounds.audiotactileTimeline.maxYear === 2026, "Audiotactile timeline bounds are stale");
  assert(asset.layoutBounds.audiotactileStructure.connectedNodeCount === 78
    && asset.layoutBounds.audiotactileStructure.isolatedNodeCount === 23, "Audiotactile structural bounds are stale");
}

function report(asset, output, snapshotOutput, wrote) {
  const result = {
    schema: asset.schema,
    wrote,
    output: path.relative(REPO_ROOT, output),
    snapshotOutput: snapshotOutput ? path.relative(REPO_ROOT, snapshotOutput) : null,
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
