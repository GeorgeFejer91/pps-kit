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
  "src/peripersonal_space_toolkit/dashboard/publication_network.v2.json",
);
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

const FOCUSED_EXPECTED = Object.freeze({
  nodes: 64,
  edges: 456,
  toolkitRecordJoins: 68,
  toolkitNodeJoins: 64,
  toolkitRunnableNodes: 15,
  toolkitRunnableRecords: 17,
  toolkitManualReviewRecords: 24,
  toolkitManualReviewNodes: 21,
  abstractsAvailable: 33,
  abstractsSourceLinkOnly: 28,
  abstractsNotAvailable: 3,
});

const SOURCE_SCHEMA = "pps-publication-citation-source.v1";
const ASSET_SCHEMA = "pps-publication-citation-network.v2";
const SNAPSHOT_ID = "pps-citation-network-20260807";
const SNAPSHOT_DATE = "2026-08-07";
const GENERATOR_VERSION = "2.0.0";
const GRID_SIZE = 8;
const GRID_MARGIN = 0.07;

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

function createSquareGrid() {
  const spacing = (1 - (2 * GRID_MARGIN)) / (GRID_SIZE - 1);
  const slots = [];
  for (let row = 0; row < GRID_SIZE; row += 1) {
    for (let column = 0; column < GRID_SIZE; column += 1) {
      const x = roundCoordinate(GRID_MARGIN + (column * spacing));
      const y = roundCoordinate(GRID_MARGIN + (row * spacing));
      slots.push({
        row,
        column,
        x,
        y,
        centerDistanceRank: (((2 * row) - (GRID_SIZE - 1)) ** 2)
          + (((2 * column) - (GRID_SIZE - 1)) ** 2),
      });
    }
  }
  const minimumCenterSpacing = slots.reduce((minimum, slot, index) => {
    for (let other = index + 1; other < slots.length; other += 1) {
      minimum = Math.min(minimum, Math.hypot(
        slot.x - slots[other].x,
        slot.y - slots[other].y,
      ));
    }
    return minimum;
  }, Number.POSITIVE_INFINITY);
  return {
    slots,
    minimumCenterSpacing: Number(minimumCenterSpacing.toFixed(6)),
  };
}

function prominenceNodeOrder(left, right) {
  return right.citations.withinCorpusReceived - left.citations.withinCorpusReceived
    || right.centrality.pageRank - left.centrality.pageRank
    || right.centrality.influence - left.centrality.influence
    || left.id.localeCompare(right.id);
}

function timelineNodeOrder(left, right) {
  const leftYear = Number.isInteger(left.year) ? left.year : Number.POSITIVE_INFINITY;
  const rightYear = Number.isInteger(right.year) ? right.year : Number.POSITIVE_INFINITY;
  return leftYear - rightYear
    || left.title.localeCompare(right.title)
    || left.id.localeCompare(right.id);
}

function createFocusedLayouts(nodes) {
  assert(nodes.length === GRID_SIZE * GRID_SIZE, `Expected ${GRID_SIZE * GRID_SIZE} focused nodes for the square grid`);
  const grid = createSquareGrid();
  const rowMajorSlots = [...grid.slots].sort((left, right) => left.row - right.row
    || left.column - right.column);
  const centerOutSlots = [...grid.slots].sort((left, right) =>
    left.centerDistanceRank - right.centerDistanceRank
    || left.row - right.row
    || left.column - right.column);
  const prominenceNodes = [...nodes].sort(prominenceNodeOrder);
  const timelineNodes = [...nodes].sort(timelineNodeOrder);
  const prominence = new Map();
  const timeline = new Map();
  prominenceNodes.forEach((node, index) => {
    const slot = centerOutSlots[index];
    prominence.set(node.id, { x: slot.x, y: slot.y });
  });
  timelineNodes.forEach((node, index) => {
    const slot = rowMajorSlots[index];
    timeline.set(node.id, { x: slot.x, y: slot.y });
  });
  const years = timelineNodes.map((node) => node.year).filter(Number.isInteger);
  return {
    prominence,
    timeline,
    minYear: Math.min(...years),
    maxYear: Math.max(...years),
    gridSize: GRID_SIZE,
    margin: GRID_MARGIN,
    minimumCenterSpacing: grid.minimumCenterSpacing,
    maximumRecommendedNodeRadius: Number((grid.minimumCenterSpacing * 0.4).toFixed(6)),
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

function isInScopeToolkitRecord(record) {
  return Boolean(record.coverageCategory)
    && record.coverageCategory !== "adjacent_out_of_scope";
}

function isFocusedExperimentalNode(node) {
  return node.corpus.documentRole !== "review"
    && node.toolkit.records.some(isInScopeToolkitRecord);
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
  const focusedNodes = joinedSourceNodes
    .filter(isFocusedExperimentalNode)
    .map((node) => ({
      ...node,
      toolkit: {
        ...node.toolkit,
        records: node.toolkit.records.filter(isInScopeToolkitRecord),
      },
    }));
  const focusedIds = new Set(focusedNodes.map((node) => node.id));
  const focusedEdges = sourceEdges.filter((edge) =>
    focusedIds.has(edge.source) && focusedIds.has(edge.target));
  const layouts = createFocusedLayouts(focusedNodes);
  const nodeIndex = new Map(focusedNodes.map((node, index) => [node.id, index]));

  const assetNodes = focusedNodes.map((node) => {
    return {
      ...node,
      layouts: {
        prominence: layouts.prominence.get(node.id),
        timeline: layouts.timeline.get(node.id),
      },
    };
  });
  const assetEdges = focusedEdges.map((edge) => [
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
    toolkitRecordJoins: assetNodes.reduce((total, node) => total + node.toolkit.records.length, 0),
    toolkitNodeJoins: assetNodes.filter((node) => node.toolkit.records.length).length,
    toolkitRunnableNodes: assetNodes.filter((node) =>
      node.toolkit.records.some((record) => record.recreatable)).length,
    toolkitRunnableRecords: assetNodes.reduce((total, node) =>
      total + node.toolkit.records.filter((record) => record.recreatable).length, 0),
    toolkitManualReviewRecords: assetNodes.reduce((total, node) =>
      total + node.toolkit.records.filter((record) => record.manualReview).length, 0),
    toolkitManualReviewNodes: assetNodes.filter((node) =>
      node.toolkit.records.some((record) => record.manualReview)).length,
    abstractsAvailable: assetNodes.filter((node) => node.abstract.status === "available").length,
    abstractsSourceLinkOnly: assetNodes.filter((node) => node.abstract.status === "source_link_only").length,
    abstractsNotAvailable: assetNodes.filter((node) => node.abstract.status === "not_available").length,
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
    sourceCounts,
    methodology: {
      edgeDirection: snapshot.sourceMethodology.edgeDirection,
      selection: "Includes a publication when an exact-DOI toolkit audit join has at least one non-empty coverage category other than adjacent_out_of_scope and the source document role is not review. The focused asset is publication-level, so multiple runnable paradigms from one paper remain one node and all in-scope audit records remain attached.",
      centrality: {
        pageRank: "Retained from the directed 1,712-publication source corpus.",
        betweennessApprox: "Retained approximate betweenness from the 1,712-publication source corpus.",
        influence: "Retained source-corpus navigation score; it is not a quality score.",
      },
      layouts: {
        prominence: "Deterministic 8 by 8 normalized square grid. Publications are ranked by source-corpus citations received, PageRank, influence, then stable ID and assigned to slots from the centre outward.",
        timeline: "Deterministic 8 by 8 normalized square grid. Publications are sorted by year, title, then stable ID and assigned row-major from top left to bottom right.",
      },
      abstracts: snapshot.sourceMethodology.abstractPolicy,
      toolkitJoin: "Toolkit literature coverage and manual parameter reviews are joined by normalized DOI only; fuzzy title/author matching is not used.",
    },
    counts,
    layoutBounds: {
      grid: {
        rows: layouts.gridSize,
        columns: layouts.gridSize,
        minX: layouts.margin,
        maxX: roundCoordinate(1 - layouts.margin),
        minY: layouts.margin,
        maxY: roundCoordinate(1 - layouts.margin),
        minimumCenterSpacing: layouts.minimumCenterSpacing,
        maximumRecommendedNodeRadius: layouts.maximumRecommendedNodeRadius,
      },
      prominence: {
        algorithm: "8x8 square grid; prominence-ranked nodes mapped to centre-out slots",
        nodeOrder: ["withinCorpusReceived desc", "pageRank desc", "influence desc", "id asc"],
        slotOrder: "distance from centre asc, row asc, column asc",
      },
      timeline: {
        algorithm: "8x8 square grid; chronological nodes mapped to row-major slots",
        nodeOrder: ["year asc (unknown last)", "title asc", "id asc"],
        minYear: layouts.minYear,
        maxYear: layouts.maxYear,
      },
    },
    facets: {
      corpusTiers: countValues(assetNodes.map((node) => node.corpus.tier)),
      themes: countValues(assetNodes.map((node) => node.corpus.theme)),
      documentRoles: countValues(assetNodes.map((node) => node.corpus.documentRole)),
      years: countValues(assetNodes.map((node) => node.year ?? "unknown")),
      edgeProvenance: countValues(focusedEdges.map((edge) => edge.provenance)),
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
  for (const [name, expected] of Object.entries(FOCUSED_EXPECTED)) {
    assert(asset.counts[name] === expected, `Expected counts.${name}=${expected}; got ${asset.counts[name]}`);
  }
  assert(asset.nodes.length === FOCUSED_EXPECTED.nodes, "Focused node array length does not match counts");
  assert(asset.edges.length === FOCUSED_EXPECTED.edges, "Focused edge array length does not match counts");
  const ids = asset.nodes.map((node) => node.id);
  assert(new Set(ids).size === ids.length, "Focused publication IDs must be unique");
  assert(ids.every((id, index) => index === 0 || ids[index - 1].localeCompare(id) <= 0), "Focused publication nodes must remain ID-sorted");
  assert(asset.nodes.every((node) => isFocusedExperimentalNode(node)), "Every focused node must satisfy the toolkit-coverage and non-review predicate");
  assert(asset.nodes.every((node) => node.toolkit.records.length > 0
    && node.toolkit.records.every(isInScopeToolkitRecord)), "Focused nodes may contain only in-scope toolkit audit records");

  const edgeKeys = new Set();
  for (const edge of asset.edges) {
    assert(Array.isArray(edge) && edge.length === 3, "Every focused edge must be [source, target, provenance]");
    const [source, target, provenance] = edge;
    assert(Number.isInteger(source) && source >= 0 && source < asset.nodes.length, "Focused edge source must resolve");
    assert(Number.isInteger(target) && target >= 0 && target < asset.nodes.length, "Focused edge target must resolve");
    assert(source !== target, "Focused citation edges must not be self-links");
    assert(typeof provenance === "string" && provenance, "Focused citation edges require provenance");
    const key = `${source}:${target}`;
    assert(!edgeKeys.has(key), `Duplicate focused citation edge ${key}`);
    edgeKeys.add(key);
  }

  const grid = createSquareGrid();
  const bounds = asset.layoutBounds.grid;
  assert(bounds.rows === GRID_SIZE && bounds.columns === GRID_SIZE, "Focused layouts must use an 8x8 grid");
  assert(bounds.minX === GRID_MARGIN && bounds.minY === GRID_MARGIN
    && bounds.maxX === roundCoordinate(1 - GRID_MARGIN)
    && bounds.maxY === roundCoordinate(1 - GRID_MARGIN), "Focused layout bounds must preserve the normalized grid margin");
  assert(bounds.minimumCenterSpacing === grid.minimumCenterSpacing, "Focused layout minimum spacing metadata is stale");
  for (const layoutName of ["prominence", "timeline"]) {
    const positions = asset.nodes.map((node) => node.layouts[layoutName]);
    assert(positions.every((position) => position
      && Number.isFinite(position.x) && Number.isFinite(position.y)
      && position.x >= bounds.minX && position.x <= bounds.maxX
      && position.y >= bounds.minY && position.y <= bounds.maxY), `All ${layoutName} coordinates must be finite and inside the normalized square bounds`);
    const slotKeys = positions.map((position) => `${position.x.toFixed(6)}:${position.y.toFixed(6)}`);
    assert(new Set(slotKeys).size === asset.nodes.length, `${layoutName} must assign one unique slot to every publication`);
    for (let index = 0; index < positions.length; index += 1) {
      for (let other = index + 1; other < positions.length; other += 1) {
        const distance = Math.hypot(
          positions[index].x - positions[other].x,
          positions[index].y - positions[other].y,
        );
        assert(distance >= bounds.minimumCenterSpacing - 1e-6, `${layoutName} publications violate the declared minimum spacing`);
      }
    }
  }

  const rowMajorSlots = [...grid.slots].sort((left, right) => left.row - right.row
    || left.column - right.column);
  const centerOutSlots = [...grid.slots].sort((left, right) =>
    left.centerDistanceRank - right.centerDistanceRank
    || left.row - right.row
    || left.column - right.column);
  [...asset.nodes].sort(prominenceNodeOrder).forEach((node, index) => {
    const slot = centerOutSlots[index];
    assert(node.layouts.prominence.x === slot.x && node.layouts.prominence.y === slot.y, "Prominence slot ordering is stale");
  });
  [...asset.nodes].sort(timelineNodeOrder).forEach((node, index) => {
    const slot = rowMajorSlots[index];
    assert(node.layouts.timeline.x === slot.x && node.layouts.timeline.y === slot.y, "Timeline slot ordering is stale");
  });
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
