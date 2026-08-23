#!/usr/bin/env node

/**
 * Build the publication-by-parameter review ledgers from tracked PPS Toolkit data.
 *
 * The 94-node focused publication network is the row authority. Publication
 * evidence is joined only through the network generator's exact-DOI record
 * joins. Manual reviews override automated evidence candidates. Toolkit
 * implementation status comes from the generated Segment 0-6 profile parameter
 * manifests, with segment-level profile gaps retained as separate columns.
 */

import fs from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

import {
  ORIENTATION_EVIDENCE_COLUMNS,
  PAPER_PARAMETER_GROUPS,
  PAPER_PARAMETERS,
  VISUALIZATION_COLUMNS,
} from "./publication_parameter_taxonomy.mjs";
import { targetCurrentBinding } from "./publication_target_current_crosswalk.mjs";

const REPO_ROOT = process.cwd();
const NETWORK_PATH = path.join(
  REPO_ROOT,
  "apps/designer/frontend/publication_network.v3.json",
);
const COVERAGE_PATH = path.join(
  REPO_ROOT,
  "For-AI/research/literature/preload-ledgers/audiotactile_literature_coverage.json",
);
const AUDIT_DIR = path.join(REPO_ROOT, "For-AI/research/literature/audiotactile-paper-metadata-audit");
const EXTRACTION_SCHEMA_PATH = path.join(AUDIT_DIR, "extraction_schema.json");
const STUDY_INSTANCE_REGISTRY_PATH = path.join(AUDIT_DIR, "study_instance_registry.json");
const CURRENT_INPUT_SCHEMA_PATH = path.join(REPO_ROOT, "For-AI/research/literature/tools/current_toolkit_input_schema.json");
const CURRENT_INPUT_BUILDER_PATH = path.join(REPO_ROOT, "For-AI/research/literature/tools/build_current_toolkit_input_matrices.py");
const PARSIMONIOUS_BUILDER_PATH = path.join(
  REPO_ROOT,
  "For-AI/research/literature/tools/build_parsimonious_publication_matrix.py",
);
const METADATA_AUDIT_PATH = path.join(AUDIT_DIR, "metadata_audit.jsonl");
const MANUAL_REVIEW_DIR = path.join(AUDIT_DIR, "manual_reviews");
const PRELOAD_DIR = path.join(REPO_ROOT, "packages/pps-resources/assets/preloads");
const outputArgumentIndex = process.argv.indexOf("--output");
const outputArgument = outputArgumentIndex >= 0 ? process.argv[outputArgumentIndex + 1] : "";
if (outputArgumentIndex >= 0 && !outputArgument) {
  throw new Error("--output requires a directory path");
}
const OUTPUT_DIR = outputArgument
  ? path.resolve(REPO_ROOT, outputArgument)
  : path.join(AUDIT_DIR, "publication-parameter-matrix");
const GENERATED_ON = "2026-08-12";
const PARSIMONIOUS_CONTRACT_COUNT = 11;
const PYTHON_EXECUTABLE = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const GENERATED_OUTPUT_FILENAMES = [
  "README.md",
  "audit_records_outside_network.csv",
  "current_input_review_queue.csv",
  "current_input_review_status_legend.csv",
  "current_input_to_target_crosswalk.csv",
  "current_toolkit_input_dictionary.csv",
  "current_toolkit_input_status_legend.csv",
  "current_toolkit_input_values.csv",
  "implementation_discrepancies.csv",
  "implementation_surface_inventory.csv",
  "parsimonious_contract_dictionary.csv",
  "parsimonious_contract_evidence.csv",
  "parsimonious_contract_review_queue.csv",
  "parsimonious_contract_summary.csv",
  "parsimonious_status_legend.csv",
  "publication_parsimonious_status_matrix.csv",
  "publication_current_input_review_matrix.csv",
  "publication_current_toolkit_input_matrix.csv",
  "publication_current_toolkit_input_values.csv",
  "publication_parameter_dictionary.csv",
  "publication_parameter_evidence_detail.csv",
  "publication_parameter_matrix.csv",
  "publication_parameter_review_queue.csv",
  "publication_parameter_status_legend.csv",
  "publication_parameter_summary.csv",
  "publication_study_index.csv",
  "publication_target_method_validation_gap_matrix.csv",
  "study_instance_current_input_review_matrix.csv",
  "study_instance_current_toolkit_input_matrix.csv",
  "study_instance_index.csv",
  "study_instance_parsimonious_status_matrix.csv",
  "study_instance_parsimonious_value_matrix.csv",
  "study_instance_target_method_evidence_sidecar.csv",
  "study_instance_target_method_validation_gap_matrix.csv",
  "study_instance_target_method_review_queue.csv",
  "study_orientation_review.csv",
  "study_visualizations.csv",
  "target_method_validation_dictionary.csv",
  "target_method_validation_group_summary.csv",
  "target_method_validation_parameter_summary.csv",
  "target_method_validation_status_legend.csv",
  "target_method_to_current_input_crosswalk.csv",
].sort();
const GENERATED_OUTPUT_MANIFEST_FILENAME = "generated_output_manifest.json";

const PROFILE_PARAMETERS = [
  {
    segment: "0",
    key: "profile_identity",
    label: "Profile identity",
    description: "Template/profile identifier, title, and experiment-variant identity.",
    toolkitPaths: "study_templates/*.json; assets/preloads/*/01_profile/profile_parameters_manifest.json",
  },
  {
    segment: "0",
    key: "publication_reference",
    label: "Publication reference",
    description: "Citation, DOI, source URL, and verification state attached to the profile.",
    toolkitPaths: "study_templates/*.json::{citation,doi,source_url,verification_status}",
  },
  {
    segment: "0",
    key: "profile_parameter_provenance",
    label: "Profile parameter provenance",
    description: "Source pointers, paper-derived values, toolkit defaults, and recreation caveats.",
    toolkitPaths: "study_templates/*.json::{reference_parameters,provenance,notes}",
  },
  {
    segment: "1",
    key: "source_stimulus_inventory",
    label: "Source stimulus inventory",
    description: "Generated/imported/baked auditory assets, source identities, hashes, and reuse boundaries.",
    toolkitPaths: "design.noises; design.custom_looming_files; design.prestimulus_files; 1_core_audio_ingredients",
  },
  {
    segment: "1",
    key: "trajectory_snapshots",
    label: "Trajectory snapshots",
    description: "Per-source motion mode, coordinate frame, start/end coordinates, distance, direction, and renderer facts.",
    toolkitPaths: "design.trajectory; design.*.trajectory_snapshot; 1_core_audio_ingredients/trajectory_inventory.json",
  },
  {
    segment: "1",
    key: "stimulus_duration",
    label: "Stimulus duration",
    description: "Auditory movement and total duration, including configured pre/post holds or imported duration.",
    toolkitPaths: "design.trajectory::{path_length_m,propagation_speed_mps,padding_pre_s,padding_post_s}; audio file specs",
  },
  {
    segment: "2",
    key: "trial_sequence_rows",
    label: "Trial sequence rows",
    description: "Named trial families and ordered fixed-audio, looming/source, alternative, and jitter elements.",
    toolkitPaths: "design.protocol.trial_strips; 2_trial_sequence_designs",
  },
  {
    segment: "2",
    key: "jitter_values_ms",
    label: "Jitter values",
    description: "Explicit within-sequence silent jitter values in milliseconds.",
    toolkitPaths: "design.protocol.trial_strips[].elements[].jitter_values_ms",
  },
  {
    segment: "2",
    key: "iti_jitter_policy",
    label: "ITI/jitter policy",
    description: "Fixed, jittered, manual, or expectancy/hazard-control timing policy encoded for trial sequencing.",
    toolkitPaths: "trial-strip jitter elements; row-level ITI/foreperiod/hazard metadata",
  },
  {
    segment: "3",
    key: "soa_values_ms",
    label: "SOA values",
    description: "Target tactile onset delays and their spatial/distance pairing.",
    toolkitPaths: "design.protocol::{soa_values_ms,spatial_values_cm,pair_spatial_values_with_soas}",
  },
  {
    segment: "3",
    key: "tactile_sites",
    label: "Tactile sites",
    description: "Tactile body site/side plus row-level modality, waveform, intensity, duration, calibration, and channel metadata.",
    toolkitPaths: "design.protocol.tactile_sites; Segment 3 row-level tactile metadata; channel 3 contract",
  },
  {
    segment: "3",
    key: "baseline_mode",
    label: "Baseline mode",
    description: "No baseline, tactile-only, anchor, stationary, SOA-zero, sound-offset, or custom baseline strategy.",
    toolkitPaths: "design.protocol::{include_baseline_trials,baseline_strategy,baseline_custom_trial_mode,baseline_soa_values_ms}",
  },
  {
    segment: "3",
    key: "baseline_count",
    label: "Baseline count",
    description: "Exact or percentage baseline allocation and whether it crosses sequence variants.",
    toolkitPaths: "design.protocol::{baseline_trials_exact,baseline_trial_percentage,baseline_crosses_sequence_variants}",
  },
  {
    segment: "3",
    key: "catch_mode",
    label: "Catch mode",
    description: "Catch/audio-only inclusion, exact or percentage allocation, and response-withhold contract.",
    toolkitPaths: "design.protocol::{include_catch_trials,catch_trials_exact,catch_trial_percentage,include_auditory_only_trials,*_crosses_sequence_variants}",
  },
  {
    segment: "4",
    key: "trial_pool_repetitions",
    label: "Trial-pool repetitions",
    description: "Global/family/row/WAV repetition counts used to produce the Segment 4 trial pool.",
    toolkitPaths: "design.protocol::{repetitions_per_condition,trial_pool_repetition_defaults}; 4_trial_repetition_pool",
  },
  {
    segment: "5",
    key: "block_count",
    label: "Block count",
    description: "Number and labels of generated block schedules.",
    toolkitPaths: "design.protocol::{blocks,block_specs}; 5_block_csv_preview",
  },
  {
    segment: "5",
    key: "row_order_constraints",
    label: "Row/order constraints",
    description: "Trial randomization, block-order randomization, maximum consecutive constraints, and preserved row scaffolds.",
    toolkitPaths: "design.protocol::{trial_randomization_strategy,block_order_randomization,max_consecutive_same_trial_type,repeat_trial_pool_per_block,distribute_trial_pool_across_blocks}",
  },
  {
    segment: "6",
    key: "participants",
    label: "Legacy order-preview count",
    description: "Legacy manifests call this participants, but the current Segment 6 contract treats it as the number of participant orders previewed, not planned sample N.",
    toolkitPaths: "legacy design.protocol.participants; canonical target toolkit.profile_finalization.order_preview_count",
  },
  {
    segment: "6",
    key: "experiment_parts",
    label: "Experiment parts",
    description: "One-part or split/pre-post package structure and part-order identity.",
    toolkitPaths: "reference_parameters.dashboard_run_setup.experiment_structure; Segment 6 run setup manifest",
  },
];

const IMPLEMENTATION_STATUS_ORDER = [
  "encoded",
  "inferred",
  "defaulted",
  "missing_publication_parameter",
  "not_encoded",
  "no_profile",
  "none",
  "gap_defaulted",
  "gap_missing",
  "mixed",
];

const PUBLICATION_READY_STATUSES = new Set([
  "reported",
  "reported_absent",
  "reported_with_caveat",
  "reported_with_toolkit_distribution",
  "source_inconsistency_caveat",
  "derived",
  "protocol_lineage_derived",
]);
const PUBLICATION_REVIEWED_STATUSES = new Set([
  ...PUBLICATION_READY_STATUSES,
  "not_reported_after_review",
]);
const PUBLICATION_ACTION_STATUSES = new Set([
  "not_assessed",
  "source_unavailable",
  "inferred_low_confidence",
  "not_reported_after_review",
  "derived",
  "protocol_lineage_derived",
  "reported_with_caveat",
  "reported_with_toolkit_distribution",
  "source_inconsistency_caveat",
  "mixed",
]);
const IMPLEMENTATION_ACTION_STATUSES = new Set([
  "no_profile",
  "not_encoded",
  "inferred",
  "defaulted",
  "missing_publication_parameter",
  "gap_defaulted",
  "gap_missing",
  "mixed",
]);

const ATOMIC_STATUS_MAP = {
  reported: "parent_reported_atomic_unreviewed",
  reported_absent: "parent_reported_absent_atomic_unreviewed",
  reported_with_caveat: "parent_caveated_atomic_unreviewed",
  reported_with_toolkit_distribution: "parent_toolkit_distribution_atomic_unreviewed",
  source_inconsistency_caveat: "parent_conflict_atomic_unreviewed",
  derived: "parent_derived_atomic_unreviewed",
  protocol_lineage_derived: "parent_lineage_derived_atomic_unreviewed",
  inferred_low_confidence: "parent_low_confidence_atomic_unreviewed",
  not_reported_after_review: "parent_reviewed_missing",
  not_applicable: "parent_not_applicable_atomic_unreviewed",
  source_unavailable: "source_unavailable",
  not_assessed: "not_assessed",
};

const ATOMIC_REVIEW_ACTIONS = {
  composite_parent_atomic_unreviewed: "disaggregate_composite_record_before_atomic_review",
  parent_reported_atomic_unreviewed: "disaggregate_reported_parent_into_atomic_value",
  parent_reported_absent_atomic_unreviewed: "verify_which_atomic_leaves_are_explicitly_absent",
  parent_caveated_atomic_unreviewed: "disaggregate_and_resolve_parent_caveat",
  parent_toolkit_distribution_atomic_unreviewed: "verify_atomic_toolkit_translation",
  parent_conflict_atomic_unreviewed: "resolve_conflicting_source_evidence",
  parent_derived_atomic_unreviewed: "verify_atomic_derivation",
  parent_lineage_derived_atomic_unreviewed: "verify_atomic_protocol_lineage",
  parent_low_confidence_atomic_unreviewed: "manually_confirm_atomic_candidate",
  parent_reviewed_missing: "recover_atomic_value_or_document_explicit_default",
  parent_not_applicable_atomic_unreviewed: "verify_atomic_not_applicable",
  source_unavailable: "acquire_or_open_source_then_review_atomic_leaf",
  not_assessed: "create_publication_audit_then_review_atomic_leaf",
  not_covered_by_current_audit: "review_new_atomic_leaf_from_primary_source",
  multiple_parent_statuses_atomic_unreviewed: "resolve_each_parent_then_review_atomic_leaf",
};

const ATOMIC_STATUS_BASE_SCORES = {
  composite_parent_atomic_unreviewed: 110,
  parent_reviewed_missing: 105,
  parent_conflict_atomic_unreviewed: 100,
  parent_caveated_atomic_unreviewed: 92,
  parent_toolkit_distribution_atomic_unreviewed: 90,
  multiple_parent_statuses_atomic_unreviewed: 88,
  parent_lineage_derived_atomic_unreviewed: 84,
  parent_derived_atomic_unreviewed: 82,
  parent_reported_atomic_unreviewed: 78,
  parent_reported_absent_atomic_unreviewed: 72,
  parent_low_confidence_atomic_unreviewed: 68,
  source_unavailable: 60,
  not_assessed: 56,
  not_covered_by_current_audit: 52,
  parent_not_applicable_atomic_unreviewed: 30,
};

const SUPPORT_PRIORITY_BONUS = {
  unsupported_structural_gap: 24,
  proxy_or_substitution: 18,
  fixed_policy_not_configurable: 16,
  freeform_metadata_only: 12,
  not_assessed: 10,
  backend_schema_only: 7,
  runtime_only: 6,
  analysis_only: 6,
  calibration_only: 6,
  derived_materialized: 3,
  first_class_gui: 0,
};

function normalizeDoi(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//, "")
    .replace(/^doi:\s*/, "")
    .replace(/[?#].*$/, "")
    .replace(/[\s.,;]+$/, "");
}

function unique(values) {
  return [...new Set(values.filter((value) => value !== undefined && value !== null && value !== ""))];
}

function aggregateStatuses(statuses, emptyStatus) {
  const values = unique(statuses.map((status) => String(status || "").trim())).sort();
  if (values.length === 0) return emptyStatus;
  if (values.length === 1) return values[0];
  return "mixed";
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = Array.isArray(value) ? value.join(" | ") : String(value);
  if (/[",\r\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function toCsv(rows, columns) {
  const header = columns.map(csvEscape).join(",");
  const body = rows.map((row) => columns.map((column) => csvEscape(row[column])).join(","));
  return `${[header, ...body].join("\n")}\n`;
}

function titleCaseKey(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function experimentLetter(index) {
  let value = Number(index) + 1;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(97 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function atomicStatusFromParentFields(fields, parentKeys, hasAuditRecord, disaggregationStatus = "") {
  if (!parentKeys.length) return "not_covered_by_current_audit";
  if (!hasAuditRecord) return "not_assessed";
  if (disaggregationStatus === "combined_record_requires_experiment_specific_review") {
    return "composite_parent_atomic_unreviewed";
  }
  const sourceStatuses = unique(
    parentKeys.map((parentKey) => fields.get(parentKey)?.status || "source_unavailable"),
  );
  const mapped = unique(sourceStatuses.map((status) => ATOMIC_STATUS_MAP[status] || "source_unavailable"));
  return mapped.length === 1 ? mapped[0] : "multiple_parent_statuses_atomic_unreviewed";
}

function joinedParentFieldText(fields, parentKeys, property) {
  return parentKeys
    .map((parentKey) => {
      const value = fields.get(parentKey)?.[property];
      if (value === undefined || value === null || value === "") return "";
      return `${parentKey}: ${formatValue(value)}`;
    })
    .filter(Boolean)
    .join(" | ");
}

function orientationStatus(manual, audit, disaggregationStatus = "") {
  if (manual?.orientation_ledger) {
    return disaggregationStatus === "combined_record_requires_experiment_specific_review"
      ? "combined_record_orientation_requires_experiment_check"
      : "structured_orientation_review_present";
  }
  if (manual) return "manual_review_missing_orientation_ledger";
  if (audit) return "not_manually_reviewed";
  return "not_assessed";
}

function atomicPriorityScore({ status, support, prominenceRank, toolkitStatus }) {
  const prominenceBonus = 20 * (1 - (prominenceRank - 1) / Math.max(1, network.nodes.length - 1));
  const toolkitBonus = toolkitStatus === "supported_incomplete" ? 12 : toolkitStatus === "runnable" ? 5 : 0;
  const scopePenalty = toolkitStatus === "adjacent_scope_conflict" ? 35 : 0;
  return Math.max(
    0,
    (ATOMIC_STATUS_BASE_SCORES[status] || 0) +
      (SUPPORT_PRIORITY_BONUS[support] || 0) +
      toolkitBonus +
      prominenceBonus -
      scopePenalty,
  );
}

function flattenSegmentFields(segmentFields) {
  const flattened = new Map();
  for (const [segmentKey, fields] of Object.entries(segmentFields || {})) {
    for (const [fieldKey, field] of Object.entries(fields || {})) {
      flattened.set(fieldKey, { segmentKey, ...(field || {}) });
    }
  }
  return flattened;
}

function formatValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function parameterAction(layer, status) {
  if (layer === "publication_evidence") {
    return {
      not_assessed: "create_literature_audit",
      source_unavailable: "acquire_or_open_source",
      inferred_low_confidence: "manually_verify_candidate",
      not_reported_after_review: "find_protocol_lineage_or_choose_explicit_default",
      derived: "verify_derivation",
      protocol_lineage_derived: "verify_protocol_lineage",
      reported_with_caveat: "resolve_or_accept_caveat",
      reported_with_toolkit_distribution: "verify_toolkit_distribution",
      source_inconsistency_caveat: "resolve_source_inconsistency",
      mixed: "review_each_experiment_variant",
    }[status] || "";
  }
  return {
    no_profile: "create_profile_after_evidence_review",
    not_encoded: "encode_parameter_in_profile",
    inferred: "verify_profile_inference",
    defaulted: "validate_default_against_publication",
    missing_publication_parameter: "recover_publication_value_or_document_default",
    gap_defaulted: "review_segment_default_or_context_gap",
    gap_missing: "resolve_blocking_segment_gap",
    mixed: "review_each_profile_variant",
  }[status] || "";
}

function actionBaseScore(action) {
  return {
    resolve_blocking_segment_gap: 105,
    recover_publication_value_or_document_default: 100,
    find_protocol_lineage_or_choose_explicit_default: 95,
    resolve_source_inconsistency: 90,
    acquire_or_open_source: 78,
    manually_verify_candidate: 72,
    create_literature_audit: 68,
    encode_parameter_in_profile: 62,
    create_profile_after_evidence_review: 55,
    review_each_experiment_variant: 52,
    review_each_profile_variant: 52,
    validate_default_against_publication: 45,
    review_segment_default_or_context_gap: 42,
    verify_protocol_lineage: 38,
    verify_derivation: 34,
    verify_profile_inference: 34,
    resolve_or_accept_caveat: 30,
    verify_toolkit_distribution: 28,
  }[action] || 0;
}

function priorityTier(score) {
  if (score >= 112) return "P0";
  if (score >= 92) return "P1";
  if (score >= 72) return "P2";
  return "P3";
}

async function loadJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function loadJsonl(filePath) {
  return (await fs.readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

async function loadJsonDirectory(directory) {
  const entries = (await fs.readdir(directory, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .sort((left, right) => left.name.localeCompare(right.name));
  return Promise.all(entries.map((entry) => loadJson(path.join(directory, entry.name))));
}

async function loadProfileManifests() {
  const entries = (await fs.readdir(PRELOAD_DIR, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .sort((left, right) => left.name.localeCompare(right.name));
  const manifests = [];
  for (const entry of entries) {
    const manifestPath = path.join(
      PRELOAD_DIR,
      entry.name,
      "01_profile/profile_parameters_manifest.json",
    );
    try {
      manifests.push(await loadJson(manifestPath));
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  return manifests;
}

const currentSchemaBuild = JSON.parse(
  execFileSync(
    PYTHON_EXECUTABLE,
    [
      CURRENT_INPUT_BUILDER_PATH,
      "--schema-only",
      "--schema-output",
      CURRENT_INPUT_SCHEMA_PATH,
    ],
    { cwd: REPO_ROOT, encoding: "utf8" },
  ),
);

const network = await loadJson(NETWORK_PATH);
const coverage = await loadJson(COVERAGE_PATH);
const extractionSchema = await loadJson(EXTRACTION_SCHEMA_PATH);
const studyInstanceRegistry = await loadJson(STUDY_INSTANCE_REGISTRY_PATH);
const currentInputSchema = await loadJson(CURRENT_INPUT_SCHEMA_PATH);
const auditRecords = await loadJsonl(METADATA_AUDIT_PATH);
const manualReviews = await loadJsonDirectory(MANUAL_REVIEW_DIR);
const profileManifests = await loadProfileManifests();

if (studyInstanceRegistry.schema !== "pps-publication-study-instance-registry.v1") {
  throw new Error(`Unexpected study-instance registry schema: ${studyInstanceRegistry.schema}`);
}
if (
  currentInputSchema.schema_version !== "current-toolkit-input-schema.v1" ||
  currentInputSchema.input_count !== 115 ||
  currentSchemaBuild.current_toolkit_input_count !== 115
) {
  throw new Error("Unexpected current Toolkit input schema; regenerate and review design.py drift");
}
const currentInputPaths = new Set(
  currentInputSchema.inputs.map((parameter) => parameter.serialized_path),
);
if (currentInputPaths.size !== currentInputSchema.input_count) {
  throw new Error("Duplicate exact current Toolkit input paths detected");
}
const targetBindingById = new Map(
  PAPER_PARAMETERS.map((parameter) => [
    parameter.parameterId,
    targetCurrentBinding(parameter, currentInputPaths),
  ]),
);

if (network.schema !== "pps-publication-citation-network.v3") {
  throw new Error(`Unexpected network schema: ${network.schema}`);
}
if (network.nodes.length !== 94) {
  throw new Error(`Expected 94 focused publication nodes, found ${network.nodes.length}`);
}
if (network.edges.length !== 750) {
  throw new Error(`Expected 750 focused citation links, found ${network.edges.length}`);
}

const publicationParameters = [];
for (const [segmentKey, fields] of Object.entries(extractionSchema.segment_fields || {})) {
  const segmentNumber = segmentKey.match(/segment_(\d+)/)?.[1] || "";
  for (const field of fields) {
    publicationParameters.push({
      layer: "publication_evidence",
      segment: segmentNumber,
      segmentKey,
      key: field.key,
      columnKey: `PUB.S${segmentNumber}.${field.key}`,
      label: field.label,
      description: field.description,
      requiredComponents: field.description,
      toolkitPaths: "See matching KIT columns and parameter checklist; evidence value remains source-derived.",
      sourcePath: "For-AI/research/literature/audiotactile-paper-metadata-audit/extraction_schema.json",
    });
  }
}
if (publicationParameters.length !== 25) {
  throw new Error(`Expected 25 publication parameters, found ${publicationParameters.length}`);
}

const implementationParameters = PROFILE_PARAMETERS.map((parameter) => ({
  layer: "toolkit_implementation",
  ...parameter,
  segmentKey: `segment_${parameter.segment}`,
  columnKey: `KIT.S${parameter.segment}.${parameter.key}`,
  requiredComponents: parameter.description,
  sourcePath: "assets/preloads/*/01_profile/profile_parameters_manifest.json",
}));
const gapParameters = ["0", "1", "2", "3", "4", "5", "6"].map((segment) => ({
  layer: "toolkit_implementation",
  segment,
  segmentKey: `segment_${segment}`,
  key: "profile_gap",
  columnKey: `KIT.S${segment}.profile_gap`,
  label: `Segment ${segment} profile gap`,
  description: `Any unresolved publication parameter, unsupported context, or declared toolkit default attached to Segment ${segment}.`,
  requiredComponents: "Review every gap note in the evidence-detail ledger; a missing gap can block launch, while a defaulted gap remains a declared recreation caveat.",
  toolkitPaths: "assets/preloads/*/01_profile/profile_parameters_manifest.json::field_inventory[parameter=profile_gap]",
  sourcePath: "assets/preloads/*/01_profile/profile_parameters_manifest.json",
}));
const allParameters = [...publicationParameters, ...implementationParameters, ...gapParameters];

const auditById = new Map(auditRecords.map((record) => [record.record_id, record]));
const manualById = new Map(manualReviews.map((record) => [record.record_id, record]));
const coverageById = new Map(
  (coverage.literature_records || []).map((record) => [record.record_id, record]),
);
const manifestByTemplate = new Map(
  profileManifests.map((manifest) => [manifest.template_id, manifest]),
);
const studyInstanceRegistryByNode = new Map(
  (studyInstanceRegistry.entries || []).map((entry) => [entry.network_node_id, entry]),
);
if (studyInstanceRegistryByNode.size !== (studyInstanceRegistry.entries || []).length) {
  throw new Error("Duplicate network_node_id in study-instance registry");
}
for (const entry of studyInstanceRegistry.entries || []) {
  const node = network.nodes.find((candidate) => candidate.id === entry.network_node_id);
  if (!node) throw new Error(`Study-instance registry node is absent from network: ${entry.network_node_id}`);
  if (normalizeDoi(node.doi) !== normalizeDoi(entry.doi)) {
    throw new Error(`Study-instance registry DOI mismatch for ${entry.network_node_id}`);
  }
  const suffixes = (entry.instances || []).map((instance) => instance.suffix);
  const expectedSuffixes = suffixes.map((_, index) => experimentLetter(index));
  if (JSON.stringify(suffixes) !== JSON.stringify(expectedSuffixes)) {
    throw new Error(`Study-instance suffixes must be sequential lowercase letters for ${entry.network_node_id}`);
  }
  const recordUseCounts = (entry.instances || []).reduce((counts, instance) => {
    if (instance.record_id) counts[instance.record_id] = (counts[instance.record_id] || 0) + 1;
    return counts;
  }, {});
  for (const instance of entry.instances || []) {
    if (
      instance.record_id &&
      recordUseCounts[instance.record_id] > 1 &&
      instance.disaggregation_status !== "combined_record_requires_experiment_specific_review"
    ) {
      throw new Error(
        `Reused composite record ${instance.record_id} lacks an experiment-disaggregation flag`,
      );
    }
  }
}

const prominenceOrder = [...network.nodes].sort(
  (left, right) =>
    Number(right.network?.prominence || 0) - Number(left.network?.prominence || 0) ||
    String(left.id).localeCompare(String(right.id)),
);
const prominenceRankById = new Map(
  prominenceOrder.map((node, index) => [node.id, index + 1]),
);

const matrixRows = [];
const studyIndexRows = [];
const evidenceRows = [];
const reviewQueueRows = [];

for (const node of network.nodes) {
  const toolkitRecords = node.toolkit?.records || [];
  const recordIds = toolkitRecords.map((record) => record.recordId).filter(Boolean);
  const templateIds = unique(
    toolkitRecords.flatMap((record) => record.templateIds || []),
  ).sort();
  const recordEvidence = recordIds.map((recordId) => {
    const audit = auditById.get(recordId) || null;
    const manual = manualById.get(recordId) || null;
    return {
      recordId,
      audit,
      manual,
      coverage: coverageById.get(recordId) || null,
      fields: flattenSegmentFields(
        manual?.segment_field_audit || audit?.segment_field_audit || {},
      ),
      sourceLayer: manual ? "manual_review" : audit ? "automated_audit" : "missing_audit_record",
    };
  });
  const rank = prominenceRankById.get(node.id);
  const manualRecordIds = recordEvidence
    .filter((record) => record.manual)
    .map((record) => record.recordId);
  const sourceStatuses = unique(
    recordEvidence.map((record) => record.audit?.pdf_status).filter(Boolean),
  ).sort();
  const supplementStatuses = unique(
    recordEvidence.map((record) => record.audit?.supplement_status).filter(Boolean),
  ).sort();
  const doiUrl = node.doi ? `https://doi.org/${normalizeDoi(node.doi)}` : String(node.links?.primary || "");
  const row = {
    node_id: node.id,
    title: node.title,
    year: node.year ?? "",
    doi: normalizeDoi(node.doi),
    publication_url: doiUrl,
    authors: (node.authors || []).join("; "),
    venue: node.venue || "",
    corpus_theme: node.corpus?.theme || "",
    document_role: node.corpus?.documentRole || "",
    toolkit_status: node.toolkit?.status || "not_assessed",
    toolkit_join_status: node.toolkit?.joinStatus || "not_audited",
    audit_record_ids: recordIds.join(" | "),
    manual_review_record_ids: manualRecordIds.join(" | "),
    template_ids: templateIds.join(" | "),
    pdf_statuses: sourceStatuses.join(" | ") || "not_assessed",
    supplement_statuses: supplementStatuses.join(" | ") || "not_assessed",
    network_prominence_rank: rank,
    network_prominence: Number(node.network?.prominence || 0),
    within_network_citations_received: Number(node.network?.inDegree || 0),
    within_network_references: Number(node.network?.outDegree || 0),
  };

  for (const parameter of publicationParameters) {
    const statuses = recordEvidence.map((record) => record.fields.get(parameter.key)?.status);
    row[parameter.columnKey] = aggregateStatuses(statuses, "not_assessed");
  }

  const manifests = templateIds.map((templateId) => manifestByTemplate.get(templateId)).filter(Boolean);
  for (const parameter of implementationParameters) {
    const statuses = manifests.map((manifest) => {
      const field = (manifest.field_inventory || []).find(
        (item) =>
          String(item.segment) === String(parameter.segment) &&
          item.parameter === parameter.key,
      );
      if (!field) return "not_encoded";
      if (field.status === "reported") return "encoded";
      return field.status || "not_encoded";
    });
    row[parameter.columnKey] = aggregateStatuses(statuses, "no_profile");
  }
  for (const parameter of gapParameters) {
    const statuses = manifests.map((manifest) => {
      const gaps = (manifest.field_inventory || []).filter(
        (item) =>
          String(item.segment) === String(parameter.segment) &&
          item.parameter === "profile_gap",
      );
      if (gaps.some((gap) => gap.status === "missing_publication_parameter")) {
        return "gap_missing";
      }
      if (gaps.length > 0) return "gap_defaulted";
      return "none";
    });
    row[parameter.columnKey] = aggregateStatuses(statuses, "no_profile");
  }

  const applicablePublicationStatuses = publicationParameters
    .map((parameter) => row[parameter.columnKey])
    .filter((status) => status !== "not_applicable");
  row.publication_fields_reviewed = applicablePublicationStatuses.filter((status) =>
    PUBLICATION_REVIEWED_STATUSES.has(status),
  ).length;
  row.publication_fields_implementation_ready = applicablePublicationStatuses.filter((status) =>
    PUBLICATION_READY_STATUSES.has(status),
  ).length;
  row.publication_fields_reviewed_missing = applicablePublicationStatuses.filter(
    (status) => status === "not_reported_after_review",
  ).length;
  row.publication_fields_requiring_review = applicablePublicationStatuses.filter(
    (status) => ["not_assessed", "source_unavailable", "inferred_low_confidence", "mixed"].includes(status),
  ).length;
  row.publication_review_progress_pct = applicablePublicationStatuses.length
    ? row.publication_fields_reviewed / applicablePublicationStatuses.length
    : 0;
  row.publication_implementation_evidence_pct = applicablePublicationStatuses.length
    ? row.publication_fields_implementation_ready / applicablePublicationStatuses.length
    : 0;
  row.toolkit_parameter_actions = [...implementationParameters, ...gapParameters].filter((parameter) =>
    IMPLEMENTATION_ACTION_STATUSES.has(row[parameter.columnKey]),
  ).length;

  matrixRows.push(row);
  studyIndexRows.push({
    node_id: row.node_id,
    title: row.title,
    year: row.year,
    doi: row.doi,
    publication_url: row.publication_url,
    authors: row.authors,
    venue: row.venue,
    corpus_theme: row.corpus_theme,
    document_role: row.document_role,
    scope_provenance: node.scope?.provenance || "",
    scope_basis: node.scope?.basis || "",
    toolkit_status: row.toolkit_status,
    toolkit_join_status: row.toolkit_join_status,
    audit_record_count: recordIds.length,
    audit_record_ids: row.audit_record_ids,
    manual_review_record_count: manualRecordIds.length,
    manual_review_record_ids: row.manual_review_record_ids,
    template_count: templateIds.length,
    template_ids: row.template_ids,
    pdf_statuses: row.pdf_statuses,
    supplement_statuses: row.supplement_statuses,
    network_prominence_rank: rank,
    network_prominence: row.network_prominence,
    within_network_citations_received: row.within_network_citations_received,
    within_network_references: row.within_network_references,
    network_component: node.network?.component ?? "",
    isolated_in_displayed_network: Boolean(node.network?.isolated),
  });

  const evidenceUnits = recordEvidence.length
    ? recordEvidence
    : [
        {
          recordId: "",
          audit: null,
          manual: null,
          coverage: null,
          fields: new Map(),
          sourceLayer: "no_exact_doi_audit_join",
        },
      ];
  for (const evidenceUnit of evidenceUnits) {
    for (const parameter of publicationParameters) {
      const field = evidenceUnit.fields.get(parameter.key) || {};
      const status = field.status || "not_assessed";
      evidenceRows.push({
        node_id: node.id,
        title: node.title,
        year: node.year ?? "",
        doi: normalizeDoi(node.doi),
        publication_url: doiUrl,
        toolkit_status: node.toolkit?.status || "not_assessed",
        record_id: evidenceUnit.recordId,
        citation_short:
          evidenceUnit.manual?.citation_short ||
          evidenceUnit.audit?.citation_short ||
          "",
        task_family:
          evidenceUnit.audit?.audiotactile_task_family ||
          evidenceUnit.coverage?.audiotactile_task_family ||
          "",
        coverage_category:
          evidenceUnit.audit?.coverage_category ||
          evidenceUnit.coverage?.coverage_category ||
          "not_assessed",
        source_layer: evidenceUnit.sourceLayer,
        manual_review_status: evidenceUnit.manual?.manual_review_status || "",
        confidence_label:
          evidenceUnit.manual?.confidence_label ||
          evidenceUnit.audit?.metadata_confidence_label ||
          "not_assessed",
        confidence_score:
          evidenceUnit.manual?.confidence_score ??
          evidenceUnit.audit?.metadata_confidence_score ??
          "",
        pdf_status: evidenceUnit.audit?.pdf_status || "not_assessed",
        supplement_status: evidenceUnit.audit?.supplement_status || "not_assessed",
        segment: parameter.segment,
        parameter_key: parameter.columnKey,
        parameter_label: parameter.label,
        field_status: status,
        value: formatValue(field.value),
        page_or_section: field.page_or_section || field.pageOrSection || "",
        evidence_note: field.evidence_note || field.evidenceNote || "",
        source_file: field.source_file || field.sourceFile || "",
      });
    }
  }

  for (const parameter of publicationParameters) {
    const status = row[parameter.columnKey];
    if (!PUBLICATION_ACTION_STATUSES.has(status)) continue;
    const action = parameterAction("publication_evidence", status);
    const prominenceBonus = 20 * (1 - (rank - 1) / Math.max(1, network.nodes.length - 1));
    const toolkitBonus = row.toolkit_status === "supported_incomplete" ? 18 : row.toolkit_status === "runnable" ? 8 : 0;
    const scopePenalty = row.toolkit_status === "adjacent_scope_conflict" ? 40 : 0;
    const score = Math.max(0, actionBaseScore(action) + toolkitBonus + prominenceBonus - scopePenalty);
    reviewQueueRows.push({
      priority_tier: priorityTier(score),
      priority_score: Number(score.toFixed(2)),
      node_id: row.node_id,
      title: row.title,
      year: row.year,
      doi: row.doi,
      publication_url: row.publication_url,
      toolkit_status: row.toolkit_status,
      network_prominence_rank: rank,
      layer: "publication_evidence",
      segment: parameter.segment,
      parameter_key: parameter.columnKey,
      parameter_label: parameter.label,
      current_status: status,
      review_action: action,
      audit_record_ids: row.audit_record_ids,
      template_ids: row.template_ids,
      source_statuses: row.pdf_statuses,
      notes: "Use Evidence Detail for per-record values and source pointers; do not infer across publication variants.",
    });
  }

  for (const parameter of [...implementationParameters, ...gapParameters]) {
    const status = row[parameter.columnKey];
    if (!IMPLEMENTATION_ACTION_STATUSES.has(status)) continue;
    const action = parameterAction("toolkit_implementation", status);
    const prominenceBonus = 20 * (1 - (rank - 1) / Math.max(1, network.nodes.length - 1));
    const toolkitBonus = row.toolkit_status === "supported_incomplete" ? 20 : row.toolkit_status === "runnable" ? 10 : 0;
    const scopePenalty = row.toolkit_status === "adjacent_scope_conflict" ? 40 : 0;
    const score = Math.max(0, actionBaseScore(action) + toolkitBonus + prominenceBonus - scopePenalty);
    const gapNotes = manifests.flatMap((manifest) =>
      (manifest.field_inventory || [])
        .filter(
          (item) =>
            parameter.key === "profile_gap" &&
            String(item.segment) === String(parameter.segment) &&
            item.parameter === "profile_gap",
        )
        .map((item) => `${manifest.template_id}: ${item.value || item.note || item.status}`),
    );
    reviewQueueRows.push({
      priority_tier: priorityTier(score),
      priority_score: Number(score.toFixed(2)),
      node_id: row.node_id,
      title: row.title,
      year: row.year,
      doi: row.doi,
      publication_url: row.publication_url,
      toolkit_status: row.toolkit_status,
      network_prominence_rank: rank,
      layer: "toolkit_implementation",
      segment: parameter.segment,
      parameter_key: parameter.columnKey,
      parameter_label: parameter.label,
      current_status: status,
      review_action: action,
      audit_record_ids: row.audit_record_ids,
      template_ids: row.template_ids,
      source_statuses: row.pdf_statuses,
      notes: gapNotes.join(" | ") || "Check the profile manifest and publication evidence before encoding a value.",
    });
  }
}

// Build the evidence-backed registered study-instance view. A publication with multiple audited
// experiments receives deterministic (a), (b), ... display suffixes while its
// immutable network, record, and template identifiers remain separate.
const studyInstanceRows = [];
const atomicEvidenceRows = [];
const atomicReviewQueueRows = [];
const orientationRows = [];
const visualizationRows = [];
const joinedNetworkRecordIds = new Set();

function experimentOrdinal(recordId) {
  const match = String(recordId || "").match(/(?:^|_)exps?_(\d+)|(?:^|_)exp(\d+)(?:_|$)/i);
  return Number(match?.[1] || match?.[2] || 9999);
}

for (const node of network.nodes) {
  const sortedRecords = [...(node.toolkit?.records || [])].sort(
    (left, right) =>
      experimentOrdinal(left.recordId) - experimentOrdinal(right.recordId) ||
      String(left.recordId || "").localeCompare(String(right.recordId || "")),
  );
  const recordsById = new Map(sortedRecords.map((record) => [record.recordId, record]));
  const registryEntry = studyInstanceRegistryByNode.get(node.id) || null;
  const recordUnits = registryEntry
    ? registryEntry.instances.map((instance) => {
        const networkRecord = instance.record_id
          ? recordsById.get(instance.record_id)
          : { recordId: "", templateIds: [] };
        if (instance.record_id && !networkRecord) {
          throw new Error(
            `Study-instance registry record ${instance.record_id} does not belong to ${node.id}`,
          );
        }
        const hasExplicitTemplateIds = Object.prototype.hasOwnProperty.call(instance, "template_ids");
        const mayInheritTemplates = [
          "record_already_experiment_specific",
          "variant_record_already_disaggregated",
        ].includes(instance.disaggregation_status);
        return {
          ...networkRecord,
          templateIds: hasExplicitTemplateIds
            ? instance.template_ids
            : mayInheritTemplates
              ? networkRecord.templateIds || []
              : [],
          suffix: instance.suffix,
          instanceKind: instance.instance_kind,
          experimentLabel: instance.experiment_label,
          inventoryStatus: registryEntry.inventory_status,
          toolkitScope: instance.toolkit_scope,
          disaggregationStatus: instance.disaggregation_status,
          instanceCountBasis: registryEntry.instance_count_basis,
          instanceEvidencePointer: registryEntry.evidence_pointer,
        };
      })
    : sortedRecords.length
      ? sortedRecords.map((record) => ({
          ...record,
          suffix: "",
          instanceKind: "review_unit",
          experimentLabel: "",
          inventoryStatus: "not_assessed",
          toolkitScope: "not_assessed",
          disaggregationStatus: "experiment_count_not_assessed",
          instanceCountBasis: "One current audit review unit; publication experiment count has not been independently registered.",
          instanceEvidencePointer: record.recordId
            ? `metadata_audit.jsonl::${record.recordId}`
            : "",
        }))
      : [{
          recordId: "",
          templateIds: [],
          suffix: "",
          instanceKind: "unassessed_publication_placeholder",
          experimentLabel: "",
          inventoryStatus: "not_assessed",
          toolkitScope: "not_assessed",
          disaggregationStatus: "experiment_count_not_assessed",
          instanceCountBasis: "No exact-DOI audit record; publication experiment count is not assessed.",
          instanceEvidencePointer: "",
        }];
  const isMultiExperiment = recordUnits.length > 1;

  for (const [recordIndex, recordUnit] of recordUnits.entries()) {
    const recordId = recordUnit.recordId || "";
    if (recordId) joinedNetworkRecordIds.add(recordId);
    const audit = auditById.get(recordId) || null;
    const manual = manualById.get(recordId) || null;
    const coverageRecord = coverageById.get(recordId) || null;
    const effective = manual || audit;
    const fields = flattenSegmentFields(effective?.segment_field_audit || {});
    const letter = recordUnit.suffix || (isMultiExperiment ? experimentLetter(recordIndex) : "");
    const studyRowId = isMultiExperiment ? `${node.id}::${letter}` : node.id;
    const studyLabel = `${node.title}${letter ? ` (${letter})` : ""}`;
    const templateIds = unique(recordUnit.templateIds || []).sort();
    const rank = prominenceRankById.get(node.id);
    const sourceLayer = manual
      ? "manual_review"
      : audit
        ? "current_audit_without_manual_review"
        : "no_exact_doi_audit_join";
    const orientationLedger = manual?.orientation_ledger || {};
    const orientationReviewStatus = orientationStatus(
      manual,
      audit,
      recordUnit.disaggregationStatus,
    );
    const doiUrl = node.doi
      ? `https://doi.org/${normalizeDoi(node.doi)}`
      : String(node.links?.primary || "");
    const identity = {
      study_row_id: studyRowId,
      network_node_id: node.id,
      record_id: recordId,
      publication_id: node.id,
      experiment_id: recordUnit.experimentLabel || recordId || "not_disaggregated",
      paradigm_variant_id: recordId || "single_or_unassessed",
      profile_id: templateIds.join(" | "),
      task_family:
        audit?.audiotactile_task_family ||
        coverageRecord?.audiotactile_task_family ||
        "not_assessed",
    };
    const studyRow = {
      ...identity,
      study_label: studyLabel,
      experiment_letter: letter,
      experiment_label: recordUnit.experimentLabel || "not_assessed",
      formal_experiment_number:
        recordUnit.experimentLabel?.match(/^Experiment\s+(\d+)/i)?.[1] || "",
      instance_kind: recordUnit.instanceKind,
      instance_inventory_status: recordUnit.inventoryStatus,
      toolkit_scope: recordUnit.toolkitScope,
      parameter_evidence_scope:
        recordUnit.disaggregationStatus === "record_already_experiment_specific"
          ? "experiment_specific"
          : recordUnit.disaggregationStatus === "variant_record_already_disaggregated"
            ? "variant_specific"
            : recordUnit.disaggregationStatus === "combined_record_requires_experiment_specific_review"
              ? "composite_requires_split"
              : "none",
      known_instance_count: registryEntry?.instances?.length || "",
      instance_count_basis: recordUnit.instanceCountBasis,
      instance_evidence_pointer: recordUnit.instanceEvidencePointer,
      experiment_disaggregation_status: recordUnit.disaggregationStatus,
      title: node.title,
      year: node.year ?? "",
      doi: normalizeDoi(node.doi),
      publication_url: doiUrl,
      toolkit_status: node.toolkit?.status || "not_assessed",
      toolkit_join_status: node.toolkit?.joinStatus || "not_audited",
      evidence_stage: sourceLayer,
      pdf_status: audit?.pdf_status || "not_assessed",
      supplement_status: audit?.supplement_status || "not_assessed",
      extraction_status: audit?.extraction_status || "not_assessed",
      manual_review_status: manual?.manual_review_status || "not_reviewed",
      orientation_review_status: orientationReviewStatus,
      visualization_review_status: audit?.pps_visualization_audit?.status || "not_assessed",
      visualization_candidate_count: audit?.pps_visualization_audit?.candidate_count || 0,
      network_prominence_rank: rank,
      network_prominence: Number(node.network?.prominence || 0),
    };

    const atomicStatusCounts = {};
    for (const parameter of PAPER_PARAMETERS) {
      const status = atomicStatusFromParentFields(
        fields,
        parameter.currentAuditParents,
        Boolean(audit),
        recordUnit.disaggregationStatus,
      );
      studyRow[parameter.parameterId] = status;
      atomicStatusCounts[status] = (atomicStatusCounts[status] || 0) + 1;

      const parentStatusText = parameter.currentAuditParents
        .map(
          (parentKey) =>
            `${parentKey}:${fields.get(parentKey)?.status || (audit ? "source_unavailable" : "not_assessed")}`,
        )
        .join(" | ");
      const sourceFileText = joinedParentFieldText(fields, parameter.currentAuditParents, "source_file");
      const pageText = joinedParentFieldText(fields, parameter.currentAuditParents, "page_or_section");
      const evidenceNoteText = joinedParentFieldText(fields, parameter.currentAuditParents, "evidence_note");
      const reviewAction = ATOMIC_REVIEW_ACTIONS[status] || "review_atomic_leaf";
      const score = atomicPriorityScore({
        status,
        support: parameter.provisionalRoutingHint,
        prominenceRank: rank,
        toolkitStatus: studyRow.toolkit_status,
      });

      atomicEvidenceRows.push({
        study_row_id: studyRowId,
        network_node_id: node.id,
        record_id: recordId,
        parameter_evidence_scope: studyRow.parameter_evidence_scope,
        target_parameter_path: parameter.parameterId,
        value_raw: "",
        value_normalized: "",
        unit: parameter.expectedUnit,
        field_status: status,
        confidence_score: manual?.confidence_score ?? audit?.metadata_confidence_score ?? "",
        confidence_label: manual?.confidence_label || audit?.metadata_confidence_label || "not_assessed",
        source_type: sourceLayer,
        source_file: sourceFileText,
        page_or_section: pageText,
        evidence_note: [
          parameter.currentAuditParents.length
            ? `coarse parents ${parameter.currentAuditParents.join("+")}; ${parentStatusText}`
            : "not covered by current 25-field audit",
          evidenceNoteText ? "see publication_parameter_evidence_detail.csv for full parent value/note" : "",
        ]
          .filter(Boolean)
          .join("; "),
        review_attempts: recordId
          ? `metadata_audit.jsonl::record_id=${recordId}::review_attempts`
          : "",
        protocol_lineage_id: parentStatusText.includes("protocol_lineage_derived")
          ? "see protocol_lineage_candidates.csv"
          : "",
        orientation_evidence_class: orientationLedger.evidence_class || "",
        provisional_implementation_hint: parameter.provisionalRoutingHint,
        target_dictionary_pointer: `target_method_validation_dictionary.csv::${parameter.parameterId}`,
        reviewer_note: "",
        review_date: "",
      });

      atomicReviewQueueRows.push({
        priority_tier: priorityTier(score),
        priority_score: Number(score.toFixed(2)),
        study_row_id: studyRowId,
        record_id: recordId,
        study_label: studyLabel,
        parameter_evidence_scope: studyRow.parameter_evidence_scope,
        target_parameter_path: parameter.parameterId,
        provisional_implementation_hint: parameter.provisionalRoutingHint,
        current_atomic_status: status,
        review_action: reviewAction,
        review_decision: "",
        value_normalized: "",
        reviewer_note: "",
        review_date: "",
      });
    }

    studyRow.atomic_parameter_count = PAPER_PARAMETERS.length;
    studyRow.atomic_review_completed_count = 0;
    studyRow.atomic_review_required_count = PAPER_PARAMETERS.length;
    studyRow.parent_reviewed_missing_count = atomicStatusCounts.parent_reviewed_missing || 0;
    studyRow.parent_source_unknown_count =
      (atomicStatusCounts.source_unavailable || 0) +
      (atomicStatusCounts.not_assessed || 0);
    studyRow.new_parameters_not_in_current_audit_count =
      atomicStatusCounts.not_covered_by_current_audit || 0;
    studyInstanceRows.push(studyRow);

    orientationRows.push({
      ...identity,
      study_label: studyLabel,
      orientation_review_status: orientationReviewStatus,
      orientation_participant_frame: orientationLedger.participant_frame || "",
      orientation_room_apparatus_frame: orientationLedger.room_apparatus_frame || "",
      orientation_body_relative_mapping: orientationLedger.body_relative_mapping || "",
      orientation_tactile_anchor: orientationLedger.tactile_anchor || "",
      orientation_movement_implementation: orientationLedger.movement_implementation || "",
      orientation_evidence_class: orientationLedger.evidence_class || "",
      ...Object.fromEntries(ORIENTATION_EVIDENCE_COLUMNS.map((column) => [column, ""])),
      review_required: orientationReviewStatus === "structured_orientation_review_present" ? "yes_visual_worksheet_extension" : "yes",
      reviewer_note: "",
      review_date: "",
    });

    const visualizationAudit = audit?.pps_visualization_audit || null;
    const candidates = visualizationAudit?.visualization_candidates || [];
    if (candidates.length) {
      candidates.forEach((candidate, candidateIndex) => {
        visualizationRows.push({
          study_row_id: studyRowId,
          visualization_id: `${studyRowId}::candidate_${candidateIndex + 1}`,
          figure_table_panel: "",
          visualization_type: candidate.visualization_type || "",
          confirmation_status:
            recordUnit.disaggregationStatus === "combined_record_requires_experiment_specific_review"
              ? "record_level_candidate_requires_experiment_check"
              : "automated_candidate_unverified",
          x_encoding: "",
          x_values: "",
          x_unit: "",
          y_metric: "",
          y_values: "",
          y_unit: "",
          model_family: "",
          model_parameters: "",
          fit_statistics: "",
          boundary_index_definition: "",
          boundary_index_value: "",
          boundary_index_unit: "",
          facets: "",
          uncertainty_encoding: "",
          visual_parameter_check: "required",
          evidence_class: "automated_text_mining_candidate",
          field_status: candidate.candidate_status || "inferred_low_confidence",
          review_note: [candidate.page_or_section, candidate.evidence_note].filter(Boolean).join(" | "),
        });
      });
    } else {
      visualizationRows.push({
        study_row_id: studyRowId,
        visualization_id: `${studyRowId}::review_required`,
        figure_table_panel: "",
        visualization_type: "",
        confirmation_status: audit ? "no_confirmed_visualization_review" : "not_assessed",
        x_encoding: "",
        x_values: "",
        x_unit: "",
        y_metric: "",
        y_values: "",
        y_unit: "",
        model_family: "",
        model_parameters: "",
        fit_statistics: "",
        boundary_index_definition: "",
        boundary_index_value: "",
        boundary_index_unit: "",
        facets: "",
        uncertainty_encoding: "",
        visual_parameter_check: "required",
        evidence_class: audit ? "no_confirmed_panel_review" : "not_assessed",
        field_status: audit
          ? visualizationAudit?.status === "no_extracted_source"
            ? "source_unavailable"
            : "review_required"
          : "not_assessed",
        review_note:
          visualizationAudit?.review_note ||
          "Inspect figures, captions, tables, supplements, axes, model annotations, boundary definitions, facets, and uncertainty displays.",
      });
    }
  }
}

if (studyInstanceRows.length !== 124) {
  throw new Error(`Expected 124 registered study-instance rows, found ${studyInstanceRows.length}`);
}
if (atomicEvidenceRows.length !== studyInstanceRows.length * PAPER_PARAMETERS.length) {
  throw new Error("Atomic evidence ledger is not a complete study-by-parameter Cartesian product");
}

studyInstanceRows.sort(
  (left, right) =>
    left.network_prominence_rank - right.network_prominence_rank ||
    String(left.study_row_id).localeCompare(String(right.study_row_id)),
);
atomicEvidenceRows.sort(
  (left, right) =>
    Number(prominenceRankById.get(left.network_node_id)) - Number(prominenceRankById.get(right.network_node_id)) ||
    String(left.study_row_id).localeCompare(String(right.study_row_id)) ||
    String(left.target_parameter_path).localeCompare(String(right.target_parameter_path)),
);
atomicReviewQueueRows.sort(
  (left, right) =>
    right.priority_score - left.priority_score ||
    left.network_prominence_rank - right.network_prominence_rank ||
    String(left.study_row_id).localeCompare(String(right.study_row_id)) ||
    String(left.target_parameter_path).localeCompare(String(right.target_parameter_path)),
);
orientationRows.sort(
  (left, right) =>
    Number(prominenceRankById.get(left.network_node_id)) - Number(prominenceRankById.get(right.network_node_id)) ||
    String(left.study_row_id).localeCompare(String(right.study_row_id)),
);
visualizationRows.sort(
  (left, right) =>
    String(left.study_row_id).localeCompare(String(right.study_row_id)) ||
    String(left.visualization_id).localeCompare(String(right.visualization_id)),
);

const studyInstancesByNode = new Map();
for (const studyRow of studyInstanceRows) {
  const values = studyInstancesByNode.get(studyRow.network_node_id) || [];
  values.push(studyRow);
  studyInstancesByNode.set(studyRow.network_node_id, values);
}
const publicationAtomicRows = network.nodes.map((node) => {
  const studyRows = studyInstancesByNode.get(node.id) || [];
  const row = {
    network_node_id: node.id,
    title: node.title,
    year: node.year ?? "",
    doi: normalizeDoi(node.doi),
    toolkit_status: node.toolkit?.status || "not_assessed",
    study_instance_count: studyRows.length,
    study_row_ids: studyRows.map((item) => item.study_row_id).join(" | "),
    record_ids: studyRows.map((item) => item.record_id).filter(Boolean).join(" | "),
    profile_ids: unique(studyRows.flatMap((item) => String(item.profile_id || "").split(" | "))).join(" | "),
    network_prominence_rank: prominenceRankById.get(node.id),
  };
  for (const parameter of PAPER_PARAMETERS) {
    row[parameter.parameterId] = aggregateStatuses(
      studyRows.map((item) => item[parameter.parameterId]),
      "not_assessed",
    );
  }
  return row;
});
publicationAtomicRows.sort(
  (left, right) =>
    left.network_prominence_rank - right.network_prominence_rank ||
    String(left.network_node_id).localeCompare(String(right.network_node_id)),
);

// Invert the target crosswalk so the primary evidence-review matrix can keep
// exact current serialized paths as its columns. This is deliberately separate
// from the current profile-encoding matrix produced from attached templates.
const targetRelationsByCurrentPath = new Map(
  currentInputSchema.inputs.map((parameter) => [parameter.serialized_path, []]),
);
for (const parameter of PAPER_PARAMETERS) {
  const binding = targetBindingById.get(parameter.parameterId);
  for (const currentPath of binding.currentSerializedPaths) {
    targetRelationsByCurrentPath.get(currentPath).push({ parameter, binding });
  }
}

const currentInputReviewCrosswalkRows = currentInputSchema.inputs.map((currentParameter) => {
  const relations = targetRelationsByCurrentPath.get(currentParameter.serialized_path);
  return {
    current_toolkit_input_path: currentParameter.serialized_path,
    parameter_group: currentParameter.parameter_group,
    type_annotation: currentParameter.type_annotation,
    value_shape: currentParameter.value_shape,
    unit: currentParameter.unit,
    mapped_target_parameter_paths: relations.map(({ parameter }) => parameter.parameterId).join(" | "),
    mapped_target_count: relations.length,
    target_binding_states: unique(
      relations.map(({ binding }) => binding.currentBindingState),
    ).join(" | "),
    current_audit_parent_fields: unique(
      relations.flatMap(({ parameter }) => parameter.currentAuditParents),
    ).join(" | "),
    current_input_contract_pointer: `current_toolkit_input_dictionary.csv::${currentParameter.serialized_path}`,
    profile_encoding_matrix_pointer: `study_instance_current_toolkit_input_matrix.csv::${currentParameter.serialized_path}`,
  };
});
const currentInputsOutsideTargetInventory = currentInputReviewCrosswalkRows.filter(
  (row) => row.mapped_target_count === 0,
);

function currentInputReviewStatus(studyRow, currentPath) {
  const relations = targetRelationsByCurrentPath.get(currentPath);
  if (!relations.length) return "not_covered_by_target_inventory";
  if (
    relations.some(
      ({ binding }) => binding.currentBindingState === "untyped_object_container_only",
    )
  ) {
    return "untyped_object_requires_key_level_review";
  }
  const statuses = unique(
    relations
      .filter(({ binding }) => binding.currentBindingState !== "derived_not_input")
      .map(({ parameter }) => studyRow[parameter.parameterId]),
  ).sort();
  if (!statuses.length) return "mapped_only_to_derived_targets";
  return statuses.length === 1 ? statuses[0] : "multiple_target_review_states";
}

function currentInputReviewAction(status) {
  if (status === "untyped_object_requires_key_level_review") {
    return "review_each_mapped_target_leaf_and_promote_method_defining_keys";
  }
  if (status === "not_covered_by_target_inventory") {
    return "classify_current_input_as_method_defining_or_operational";
  }
  if (status === "mapped_only_to_derived_targets") {
    return "validate_computed_target_against_publication";
  }
  if (status === "multiple_target_review_states") {
    return "review_each_mapped_target_leaf";
  }
  return ATOMIC_REVIEW_ACTIONS[status] || "review_current_input_against_publication";
}

const currentInputReviewRows = studyInstanceRows.map((studyRow) => {
  const row = {
    study_row_id: studyRow.study_row_id,
    network_node_id: studyRow.network_node_id,
    record_id: studyRow.record_id,
    study_label: studyRow.study_label,
    experiment_letter: studyRow.experiment_letter,
    experiment_label: studyRow.experiment_label,
    parameter_evidence_scope: studyRow.parameter_evidence_scope,
    toolkit_scope: studyRow.toolkit_scope,
    profile_ids: studyRow.profile_id,
  };
  for (const parameter of currentInputSchema.inputs) {
    row[parameter.serialized_path] = currentInputReviewStatus(
      studyRow,
      parameter.serialized_path,
    );
  }
  return row;
});

const currentInputReviewQueueRows = currentInputReviewRows.flatMap((reviewRow) =>
  currentInputSchema.inputs.map((currentParameter) => {
    const relations = targetRelationsByCurrentPath.get(currentParameter.serialized_path);
    const status = reviewRow[currentParameter.serialized_path];
    return {
      study_row_id: reviewRow.study_row_id,
      network_node_id: reviewRow.network_node_id,
      record_id: reviewRow.record_id,
      study_label: reviewRow.study_label,
      parameter_evidence_scope: reviewRow.parameter_evidence_scope,
      current_toolkit_input_path: currentParameter.serialized_path,
      current_review_status: status,
      review_action: currentInputReviewAction(status),
      mapped_target_parameter_paths: relations.map(({ parameter }) => parameter.parameterId).join(" | "),
      current_audit_parent_fields: unique(
        relations.flatMap(({ parameter }) => parameter.currentAuditParents),
      ).join(" | "),
      profile_encoding_matrix_pointer: `study_instance_current_toolkit_input_matrix.csv::${reviewRow.study_row_id}::${currentParameter.serialized_path}`,
      review_decision: "",
      value_normalized: "",
      reviewer_note: "",
      review_date: "",
    };
  }),
);

const currentReviewRowsByNode = new Map();
for (const row of currentInputReviewRows) {
  const values = currentReviewRowsByNode.get(row.network_node_id) || [];
  values.push(row);
  currentReviewRowsByNode.set(row.network_node_id, values);
}
const publicationCurrentInputReviewRows = network.nodes.map((node) => {
  const rows = currentReviewRowsByNode.get(node.id) || [];
  const result = {
    network_node_id: node.id,
    title: node.title,
    year: node.year ?? "",
    doi: normalizeDoi(node.doi),
    toolkit_status: node.toolkit?.status || "not_assessed",
    study_instance_count: rows.length,
    study_row_ids: rows.map((row) => row.study_row_id).join(" | "),
  };
  for (const parameter of currentInputSchema.inputs) {
    result[parameter.serialized_path] = aggregateStatuses(
      rows.map((row) => row[parameter.serialized_path]),
      "not_assessed",
    );
  }
  return result;
});

const fullDictionaryRows = PAPER_PARAMETERS.map((parameter, index) => {
  const binding = targetBindingById.get(parameter.parameterId);
  return {
    display_order: index + 1,
    target_parameter_path: parameter.parameterId,
    atomic_key: parameter.key,
    parameter_group: parameter.groupLabel,
    segment_or_namespace: parameter.segment,
    parameter_role:
      parameter.provisionalRoutingHint === "derived_materialized"
        ? "reported_or_target_validation_input"
        : "configuration_input",
    value_shape: parameter.valueShape,
    expected_unit: parameter.expectedUnit,
    repeating_entity: parameter.repeatableEntity,
    current_audit_parent_fields: parameter.currentAuditParents.join(" | "),
    current_audit_coverage: parameter.currentAuditParents.length
      ? "coarse_parent_only_atomic_review_required"
      : "not_covered_by_current_25_field_audit",
    current_design_binding_state: binding.currentBindingState,
    current_serialized_paths: binding.currentSerializedPaths.join(" | "),
    current_crosswalk_cardinality: binding.currentSerializedPaths.length,
    current_binding_basis: binding.bindingBasis,
    crosswalk_scope: "current StimulusDesign design_from_dict/design_to_dict contract only",
    provisional_implementation_hint: parameter.provisionalRoutingHint,
    prior_inventory_routing_note: parameter.toolkitPath,
    target_schema_requirement: "Each target leaf must be typed, serializable, source-attributed, reviewable, and preserved through profile generation and runtime/analysis consumers where applicable before it can be called implemented.",
    manual_review_prompt: `Recover and verify ${titleCaseKey(parameter.key)} as the value for ${parameter.parameterId}.`,
  };
});
const targetCrosswalkRows = fullDictionaryRows.map((row) => ({
  target_parameter_path: row.target_parameter_path,
  parameter_group: row.parameter_group,
  current_design_binding_state: row.current_design_binding_state,
  current_serialized_paths: row.current_serialized_paths,
  current_crosswalk_cardinality: row.current_crosswalk_cardinality,
  current_binding_basis: row.current_binding_basis,
  crosswalk_scope: row.crosswalk_scope,
}));

const fullSummaryRows = PAPER_PARAMETERS.map((parameter) => {
  const statuses = studyInstanceRows.map((row) => row[parameter.parameterId]);
  const binding = targetBindingById.get(parameter.parameterId);
  const counts = Object.fromEntries(
    unique(statuses)
      .sort()
      .map((status) => [status, statuses.filter((value) => value === status).length]),
  );
  return {
    target_parameter_path: parameter.parameterId,
    parameter_group: parameter.groupLabel,
    segment_or_namespace: parameter.segment,
    current_design_binding_state: binding.currentBindingState,
    current_serialized_paths: binding.currentSerializedPaths.join(" | "),
    provisional_implementation_hint: parameter.provisionalRoutingHint,
    study_instance_count: studyInstanceRows.length,
    atomic_review_required_count: statuses.length,
    parent_reported_or_derived_count: statuses.filter((status) =>
      [
        "parent_reported_atomic_unreviewed",
        "parent_reported_absent_atomic_unreviewed",
        "parent_caveated_atomic_unreviewed",
        "parent_toolkit_distribution_atomic_unreviewed",
        "parent_derived_atomic_unreviewed",
        "parent_lineage_derived_atomic_unreviewed",
      ].includes(status),
    ).length,
    parent_reviewed_missing_count: statuses.filter((status) => status === "parent_reviewed_missing").length,
    source_unknown_count: statuses.filter((status) => ["source_unavailable", "not_assessed"].includes(status)).length,
    not_covered_by_current_audit_count: statuses.filter((status) => status === "not_covered_by_current_audit").length,
    status_counts_json: JSON.stringify(counts),
  };
});

const outsideReasonByRecordId = {
  serino_2011_professional_fencers: "no DOI; cannot exact-DOI join to network",
  novel_two_phase_audio_tactile_2025: "no DOI; cannot exact-DOI join to network",
  teramoto_2013_visual_deprivation: "DOI belongs to a review node excluded from the focused empirical network",
  lower_limb_pps_2017: "adjacent/out-of-scope DOI excluded from focused network",
  spiousas_2025_auditory_only: "adjacent/auditory-only DOI excluded from focused network",
  barumerli_2026_semantic_looming_auditory_only: "adjacent/auditory-only DOI excluded from focused network",
};
const outsideAuditRows = auditRecords
  .filter((record) => !joinedNetworkRecordIds.has(record.record_id))
  .map((record) => ({
    record_id: record.record_id,
    citation_short: record.citation_short || "",
    doi: normalizeDoi(record.doi),
    doi_url: record.doi_url || "",
    task_family: record.audiotactile_task_family || "",
    coverage_category: record.coverage_category || "",
    pdf_status: record.pdf_status || "",
    extraction_status: record.extraction_status || "",
    exclusion_reason: outsideReasonByRecordId[record.record_id] || "not joined to focused network",
  }))
  .sort((left, right) => left.record_id.localeCompare(right.record_id));
if (outsideAuditRows.length !== 6) {
  throw new Error(`Expected 6 audit records outside the focused network, found ${outsideAuditRows.length}`);
}

const implementationSurfaceRows = [
  ["current_design_serialized_inputs", 115, "current_profile_input_contract", "primary", "tools/current_toolkit_input_schema.json", "Exact paths derived from StimulusDesign dataclasses and verified against design_from_dict/design_to_dict; arbitrary dict fields remain atomic."],
  ["proposed_target_method_validation_leaves", 281, "future_method_validation_inventory", "secondary", "tools/publication_parameter_taxonomy.mjs", "Secondary scientific-method/validation-gap review: 275 configuration candidates plus six reported/target validation leaves. These are neither current serialized Toolkit paths nor a superset of every current operational/identity input."],
  ["current_publication_audit_composites", 25, "evidence", "no", "For-AI/research/literature/audiotactile-paper-metadata-audit/extraction_schema.json", "Coarse Segment 1-4 parents retained only to bootstrap atomic review."],
  ["current_recreation_gate_segments_0_to_4", 15, "readiness_check", "no", "src/peripersonal_space_toolkit/profile_recreation.py", "Current authoritative gate is a coarse subset, not the final schema."],
  ["legacy_extended_profile_inventory_segments_0_to_6", 19, "readiness_check", "no", "assets/preloads/*/01_profile/profile_parameters_manifest.json", "Includes legacy Segment 6 participant/part labels; participant count is order-preview count."],
  ["design_dataclass_attributes", 108, "current_code_input_surface", "expanded_to_115_paths", "src/peripersonal_space_toolkit/design.py", "108 attributes expand to 115 exact paths because AudioFileSpec is used by two separate collections; the new display colour and retained source-input path are implementation bookkeeping, not additional paper-extraction contracts."],
  ["gui_method_coverage_rows", 51, "gui_input_surface", "not_path_validated_here", "For-AI GUI method audit", "51 method-bearing rows plus 13 non-method controls; GUI binding claims require separate control-to-serializer tests."],
  ["runtime_capture_options", 14, "runtime_policy_input", "namespace_only", "src/peripersonal_space_toolkit/session_runner.py::SessionCaptureOptions", "Operational capture policy; only paper-defining choices belong in study review."],
  ["normalized_loudness_leaves", 32, "input_policy_and_derived", "mapped_subset", "src/peripersonal_space_toolkit/loudness.py::normalize_loudness_policy", "26 inputs/policies, five derived values, one schema field."],
  ["tactile_calibration_policy_constants", 27, "calibration_policy_input", "namespace_only", "src/peripersonal_space_toolkit/tactile_calibration", "Include only paper-defining calibration policy in the per-study matrix."],
  ["tactile_calibration_run_inputs", 7, "calibration_run_input", "namespace_only", "src/peripersonal_space_toolkit/tactile_calibration", "Operational run identity/paths and current output levels."],
  ["adaptive_tactile_inputs", 7, "runtime_policy_input", "namespace_only", "src/peripersonal_space_toolkit/tactile_threshold_adaptation.py", "Runtime adaptation policy inputs."],
  ["topup_policy_inputs", 7, "runtime_analysis_policy_input", "mapped_subset", "src/peripersonal_space_toolkit/topup.py", "Paper-relevant policy is represented in runtime/analysis inputs."],
  ["latency_validation_config", 22, "calibration_policy_input", "namespace_only", "src/peripersonal_space_toolkit/latency_validation.py", "Eight pulse-train controls, four route controls, ten thresholds."],
  ["rich_participant_trial_schema", 130, "output_evidence", "no", "runner participant output schema", "Materialized evidence/output, not paper input columns."],
  ["public_data_min", 18, "output_evidence", "no", "output field dictionary / session runner", "Public minimized export has 18 fields; older manuscript matrix says 17."],
  ["tactile_calibration_trial_fields", 33, "output_evidence", "no", "tactile calibration TRIAL_FIELDNAMES", "Evidence output, not configuration input."],
  ["adaptive_adjustment_fields", 15, "output_evidence", "no", "src/peripersonal_space_toolkit/tactile_threshold_adaptation.py", "Adjustment dataclass output; CSV adds schema metadata."],
  ["topup_ledger_fields", 39, "output_evidence", "no", "src/peripersonal_space_toolkit/topup.py", "Ledger output, not configuration input."],
  ["analysis_result_artifact_groups", 16, "output_evidence", "no", "src/peripersonal_space_toolkit/session_analysis.py::SessionAnalysisResult", "Analysis artifacts and QC, not paper input columns."],
].map(([namespace, fieldCount, role, matrixTreatment, sourcePath, note]) => ({
  namespace,
  field_count: fieldCount,
  role: role,
  primary_matrix_treatment: matrixTreatment,
  source_path: sourcePath,
  note,
}));

const discrepancyRows = [
  ["D01", "critical", "Audit granularity", "Current extraction schema has 25 composite fields limited to Segments 1-4.", "Use the 281-leaf method/validation gap inventory and evidence sidecar to decide which candidates should become typed inputs; six leaves are validation targets, and the inventory is not a current serializer contract."],
  ["D02", "critical", "Readiness gate granularity", "Current recreation gate has 15 checks through Segment 4; legacy inventory reaches 19 with overlap.", "Generate gate status from typed leaves rather than generic profile_gap rows."],
  ["D03", "high", "Segment 6 participant semantics", "Legacy participants is used/named like planned N although current contract defines order-preview count.", "Separate target.study.planned_sample_n from target.profile_finalization.order_preview_count."],
  ["D04", "high", "Participant-order algorithm", "Registry requires seeded_factoradic_cycle.v1; design enum exposes rotation, seeded permutation, and fixed.", "Add/version the canonical factoradic policy or reconcile the registry."],
  ["D05", "critical", "Typed design coverage", "Detailed tactile, response, orientation, speaker switching, visual, and MR inputs often live only in free-form metadata/output rows.", "Promote required leaves to typed, validated input schemas."],
  ["D06", "high", "Untyped dictionaries", "source_profile_parameters, participant_order_policy, and row metadata are untyped dictionaries.", "Replace/validate them with versioned structured models."],
  ["D07", "high", "Loudness GUI coverage", "Normalized loudness has 32 leaves but GUI exposes only headline controls.", "Expose or deliberately lock every method-defining loudness policy."],
  ["D08", "high", "Tactile safety/flow documentation", "For-AI module map says 0.5% ceiling and automatic return; code/newer handoff use 0.7%, 1.0% hard guard, and explicit Continue.", "Reconcile documentation, code, and qualification protocol before release."],
  ["D09", "medium", "Data_min count", "Manuscript evidence says 17 fields; code/dictionary contain 18.", "Regenerate manuscript evidence from the authoritative field dictionary."],
  ["D10", "high", "Segment folder contract", "Legacy preload folders use 01_profile through 05_run_setup while registry defines Segments 0-6.", "Version/migrate generated artifact folders and manifests."],
  ["D11", "medium", "Model-selection criterion", "Legacy comparison uses AIC while condition-lens triage uses AICc.", "Make the selected criterion an explicit analysis input."],
  ["D12", "high", "Trajectory elevation", "TrajectorySpec has one elevation scalar while publications/output may require separate start/end elevations.", "Add typed start/end elevation inputs and migration rules."],
].map(([discrepancyId, severity, area, currentState, requiredResolution]) => ({
  discrepancy_id: discrepancyId,
  severity,
  area,
  current_state: currentState,
  required_resolution: requiredResolution,
}));

matrixRows.sort(
  (left, right) =>
    Number(left.network_prominence_rank) - Number(right.network_prominence_rank) ||
    String(left.node_id).localeCompare(String(right.node_id)),
);
studyIndexRows.sort(
  (left, right) =>
    Number(left.network_prominence_rank) - Number(right.network_prominence_rank) ||
    String(left.node_id).localeCompare(String(right.node_id)),
);
evidenceRows.sort(
  (left, right) =>
    Number(prominenceRankById.get(left.node_id)) - Number(prominenceRankById.get(right.node_id)) ||
    String(left.record_id).localeCompare(String(right.record_id)) ||
    Number(left.segment) - Number(right.segment) ||
    String(left.parameter_key).localeCompare(String(right.parameter_key)),
);
reviewQueueRows.sort(
  (left, right) =>
    Number(right.priority_score) - Number(left.priority_score) ||
    Number(left.network_prominence_rank) - Number(right.network_prominence_rank) ||
    String(left.layer).localeCompare(String(right.layer)) ||
    String(left.parameter_key).localeCompare(String(right.parameter_key)),
);

const dictionaryRows = allParameters.map((parameter, index) => ({
  display_order: index + 1,
  layer: parameter.layer,
  segment: parameter.segment,
  parameter_key: parameter.columnKey,
  parameter_label: parameter.label,
  description: parameter.description,
  required_components_for_full_implementation: parameter.requiredComponents,
  toolkit_field_or_artifact_paths: parameter.toolkitPaths,
  source_definition: parameter.sourcePath,
  matrix_scope_note:
    parameter.layer === "publication_evidence"
      ? "Categorical evidence status aggregated to publication node; exact experiment-level values remain in Evidence Detail."
      : "Categorical encoding status aggregated across every profile variant attached to the publication node.",
}));

const summaryRows = allParameters.map((parameter) => {
  const statuses = matrixRows.map((row) => row[parameter.columnKey]);
  const counts = Object.fromEntries(
    unique(statuses)
      .sort()
      .map((status) => [status, statuses.filter((value) => value === status).length]),
  );
  const actionCount = statuses.filter((status) =>
    parameter.layer === "publication_evidence"
      ? PUBLICATION_ACTION_STATUSES.has(status)
      : IMPLEMENTATION_ACTION_STATUSES.has(status),
  ).length;
  return {
    layer: parameter.layer,
    segment: parameter.segment,
    parameter_key: parameter.columnKey,
    parameter_label: parameter.label,
    publication_count: matrixRows.length,
    action_required_count: actionCount,
    action_required_pct: actionCount / matrixRows.length,
    status_counts_json: JSON.stringify(counts),
    top_review_action:
      [...new Set(statuses)]
        .map((status) => ({
          status,
          action: parameterAction(parameter.layer, status),
          count: statuses.filter((value) => value === status).length,
        }))
        .filter((item) => item.action)
        .sort((left, right) => right.count - left.count || left.status.localeCompare(right.status))[0]?.action || "none",
  };
});

const legendRows = [
  ["publication_evidence", "reported", "Source directly reports the parameter.", "No", "Implement from the cited value after ordinary verification."],
  ["publication_evidence", "reported_absent", "Source explicitly reports that the element is absent.", "No", "Encode the explicit absence; do not treat it as a blank."],
  ["publication_evidence", "reported_with_caveat", "Reported value has a bounded caveat.", "Yes", "Resolve or accept the caveat before an exact-recreation claim."],
  ["publication_evidence", "reported_with_toolkit_distribution", "Source value is represented through a declared toolkit distribution.", "Yes", "Verify the distribution is an acceptable translation."],
  ["publication_evidence", "source_inconsistency_caveat", "Tracked sources disagree.", "Yes", "Resolve the inconsistency or preserve both variants."],
  ["publication_evidence", "derived", "Value is arithmetically or visually derived from reported evidence.", "Yes", "Check the derivation and coordinate frame."],
  ["publication_evidence", "protocol_lineage_derived", "Value comes from a cited predecessor protocol.", "Yes", "Verify that inheritance is justified for this study."],
  ["publication_evidence", "inferred_low_confidence", "Automated source-mining candidate; not manually confirmed.", "Yes", "Inspect the primary source/figure/supplement."],
  ["publication_evidence", "not_reported_after_review", "Full review did not recover the parameter.", "Yes", "Inspect lineage or choose and document an explicit toolkit default."],
  ["publication_evidence", "source_unavailable", "No usable source was available to the audit.", "Yes", "Acquire/open the paper or supplement."],
  ["publication_evidence", "not_applicable", "Parameter is not applicable to the study design.", "No", "Preserve as explicit not-applicable."],
  ["publication_evidence", "not_assessed", "No exact-DOI paper-audit record joins to the network node.", "Yes", "Create a literature audit before templating."],
  ["publication_evidence", "mixed", "Multiple experiment records under one publication have different statuses.", "Yes", "Review each record/variant in Evidence Detail."],
  ["toolkit_implementation", "encoded", "All attached profiles encode the field as reported.", "No", "Verify values against evidence before exact-recreation claims."],
  ["toolkit_implementation", "inferred", "The profile encodes an inferred value.", "Yes", "Verify or replace the inference."],
  ["toolkit_implementation", "defaulted", "The profile uses an explicit toolkit default.", "Yes", "Validate the default against the study or retain a caveat."],
  ["toolkit_implementation", "missing_publication_parameter", "Profile manifest flags the parameter as missing.", "Yes", "Recover the source value or document a deliberate default."],
  ["toolkit_implementation", "not_encoded", "An attached profile lacks the expected gate field.", "Yes", "Add the field to the profile manifest."],
  ["toolkit_implementation", "no_profile", "No current toolkit profile is attached to this publication.", "Yes", "Create a profile only after evidence review."],
  ["toolkit_implementation", "none", "No segment-level profile gap is declared.", "No", "No gap action from this column."],
  ["toolkit_implementation", "gap_defaulted", "A nonblocking/defaulted segment gap is declared.", "Yes", "Review the caveat and decide whether to implement it."],
  ["toolkit_implementation", "gap_missing", "A blocking missing-publication parameter is declared in the segment.", "Yes", "Resolve before launch readiness."],
  ["toolkit_implementation", "mixed", "Attached profile variants differ in encoding/gap status.", "Yes", "Review each profile variant."],
].map(([layer, status, meaning, manualReviewRequired, action]) => ({
  layer,
  status,
  meaning,
  manual_review_required: manualReviewRequired,
  recommended_action: action,
}));

const fullLegendRows = [
  ["atomic_review_status", "composite_parent_atomic_unreviewed", "The only available audit record combines multiple experiments, so no parent value is experiment-specific.", "Disaggregate the source record by experiment before accepting any atomic value."],
  ["atomic_review_status", "parent_reported_atomic_unreviewed", "A coarse audit parent is reported, but this target method/validation leaf has not been separately verified.", "Disaggregate the parent evidence and enter the atomic value."],
  ["atomic_review_status", "parent_reported_absent_atomic_unreviewed", "A coarse parent is explicitly absent; applicability/absence of this individual leaf still needs confirmation.", "Verify which leaves are absent versus not applicable."],
  ["atomic_review_status", "parent_caveated_atomic_unreviewed", "The coarse parent is reported with a caveat.", "Recover the leaf and preserve/resolve the caveat."],
  ["atomic_review_status", "parent_toolkit_distribution_atomic_unreviewed", "The parent is represented with a Toolkit distribution rather than one source-exact value.", "Verify the target-leaf translation."],
  ["atomic_review_status", "parent_conflict_atomic_unreviewed", "Tracked sources conflict at the parent level.", "Resolve the source conflict before encoding the leaf."],
  ["atomic_review_status", "parent_derived_atomic_unreviewed", "The parent contains a derived value.", "Verify the derivation at this leaf's unit/frame."],
  ["atomic_review_status", "parent_lineage_derived_atomic_unreviewed", "The parent comes from a cited predecessor protocol.", "Verify lineage applicability to this experiment."],
  ["atomic_review_status", "parent_low_confidence_atomic_unreviewed", "Only an automated/weak parent candidate exists.", "Inspect the primary source and confirm the atomic value."],
  ["atomic_review_status", "parent_reviewed_missing", "Critical review found the parent unreported.", "Inspect lineage or choose/document an explicit default."],
  ["atomic_review_status", "parent_not_applicable_atomic_unreviewed", "The coarse parent is not applicable.", "Confirm applicability for this individual leaf."],
  ["atomic_review_status", "source_unavailable", "An audit record exists but usable evidence for the parent is absent or not yet extracted.", "Acquire/open and review the source."],
  ["atomic_review_status", "not_assessed", "No exact-DOI audit record joins to this network publication.", "Create a publication audit."],
  ["atomic_review_status", "not_covered_by_current_audit", "The target method/validation leaf has no parent in the current 25-field extraction schema.", "Review the new atomic leaf directly from source."],
  ["atomic_review_status", "multiple_parent_statuses_atomic_unreviewed", "This leaf maps to multiple coarse parents with different states.", "Resolve each parent before atomic entry."],
  ["atomic_review_status", "mixed", "Study instances under the same publication differ.", "Use the registered study-instance matrix rather than the aggregate node row."],
  ["current_design_binding", "typed_current_input", "The target concept has a conservative direct binding to one or more exact current serialized design paths.", "Review the exact path values and publication evidence."],
  ["current_design_binding", "typed_current_input_with_transform", "A current typed input exists but units or representation must be transformed.", "Verify the transformation explicitly."],
  ["current_design_binding", "composite_over_typed_current_inputs", "The target concept spans multiple exact current typed inputs.", "Review every mapped path together."],
  ["current_design_binding", "partial_or_proxy_current_input", "The current typed field represents only part of the target concept or an approximation.", "Treat the uncovered portion as an implementation gap."],
  ["current_design_binding", "untyped_object_container_only", "The value can be stored in an arbitrary object but lacks its own typed serializer field.", "Promote it to a typed input when method-defining."],
  ["current_design_binding", "derived_not_input", "The target value is computed from current inputs rather than entered directly.", "Keep source target and computed value in validation evidence."],
  ["current_design_binding", "not_in_current_design_serializer", "No conservative binding to the current StimulusDesign serializer was established.", "Implement a typed input or trace a separate versioned runtime/analysis contract."],
  ["provisional_routing_hint", "first_class_gui", "Earlier inventory suggested a GUI route; this is unverified until an exact serialized-path binding test exists.", "Confirm against the current-input crosswalk and a control-to-serializer test."],
  ["provisional_routing_hint", "backend_schema_only", "Earlier inventory suggested a backend route; this is unverified until an exact parser/serializer binding exists.", "Confirm against the current-input crosswalk."],
  ["provisional_routing_hint", "runtime_only", "Likely belongs to runtime configuration rather than the current study-design serializer.", "Trace the exact runtime input contract."],
  ["provisional_routing_hint", "analysis_only", "Likely belongs to analysis configuration rather than the current study-design serializer.", "Trace the exact analysis input contract."],
  ["provisional_routing_hint", "calibration_only", "Likely belongs to calibration configuration rather than the current study-design serializer.", "Trace the exact calibration input contract."],
  ["provisional_routing_hint", "freeform_metadata_only", "Likely retained only in an untyped/free-form object.", "Promote to a typed input if it is method-defining."],
  ["provisional_routing_hint", "derived_materialized", "Likely computed/materialized rather than accepted as a primary design input.", "Keep as validation evidence unless a real input binding is traced."],
  ["provisional_routing_hint", "fixed_policy_not_configurable", "Toolkit behavior appears fixed rather than profile-configurable.", "Expose a typed policy only when publications differ."],
  ["provisional_routing_hint", "proxy_or_substitution", "Toolkit may only approximate or substitute the source method.", "Document the equivalence boundary and caveat."],
  ["provisional_routing_hint", "unsupported_structural_gap", "No candidate typed structure was found in the earlier inventory.", "Confirm against the exact crosswalk, then implement and validate."],
  ["provisional_routing_hint", "not_assessed", "No route has been assessed.", "Trace code, serializer, and production consumers."],
].map(([legendType, status, meaning, manualAction]) => ({
  legend_type: legendType,
  status,
  meaning,
  manual_action: manualAction,
}));
const currentInputReviewLegendRows = [
  ...fullLegendRows
    .filter((row) => row.legend_type === "atomic_review_status")
    .map((row) => ({
      current_review_status: row.status,
      meaning: row.meaning,
      manual_action: row.manual_action,
    })),
  {
    current_review_status: "untyped_object_requires_key_level_review",
    meaning: "One current serialized object holds multiple target concepts without typed keys.",
    manual_action: "Review each mapped target leaf and promote method-defining keys to a versioned typed contract.",
  },
  {
    current_review_status: "not_covered_by_target_inventory",
    meaning: "The current input has no mapping in the proposed scientific target taxonomy.",
    manual_action: "Classify it as method-defining or operational, then add a target mapping if needed.",
  },
  {
    current_review_status: "mapped_only_to_derived_targets",
    meaning: "The current input contributes only to computed target values.",
    manual_action: "Validate the computed value against the publication target rather than entering it twice.",
  },
  {
    current_review_status: "multiple_target_review_states",
    meaning: "Target leaves mapped to this exact current input have different evidence states.",
    manual_action: "Review each mapped target leaf in the long queue.",
  },
];

const fullGroupSummaryRows = PAPER_PARAMETER_GROUPS.map((groupDefinition) => {
  const parameters = PAPER_PARAMETERS.filter((parameter) => parameter.groupId === groupDefinition.id);
  const supportCounts = parameters.reduce((counts, parameter) => {
    counts[parameter.provisionalRoutingHint] = (counts[parameter.provisionalRoutingHint] || 0) + 1;
    return counts;
  }, {});
  const bindingCounts = parameters.reduce((counts, parameter) => {
    const state = targetBindingById.get(parameter.parameterId).currentBindingState;
    counts[state] = (counts[state] || 0) + 1;
    return counts;
  }, {});
  return {
    parameter_group: groupDefinition.label,
    segment_or_namespace: groupDefinition.segment,
    final_input_leaf_count: parameters.length,
    leaves_with_current_audit_parent: parameters.filter((parameter) => parameter.currentAuditParents.length).length,
    new_atomic_audit_leaves: parameters.filter((parameter) => !parameter.currentAuditParents.length).length,
    unsupported_structural_gap_count: parameters.filter(
      (parameter) => parameter.provisionalRoutingHint === "unsupported_structural_gap",
    ).length,
    study_instance_count: studyInstanceRows.length,
    categorical_cells_for_review: parameters.length * studyInstanceRows.length,
    current_design_binding_counts_json: JSON.stringify(bindingCounts),
    provisional_routing_hint_counts_json: JSON.stringify(supportCounts),
  };
});

const matrixMetadataColumns = [
  "node_id",
  "title",
  "year",
  "doi",
  "publication_url",
  "authors",
  "venue",
  "corpus_theme",
  "document_role",
  "toolkit_status",
  "toolkit_join_status",
  "audit_record_ids",
  "manual_review_record_ids",
  "template_ids",
  "pdf_statuses",
  "supplement_statuses",
  "network_prominence_rank",
  "network_prominence",
  "within_network_citations_received",
  "within_network_references",
  "publication_fields_reviewed",
  "publication_fields_implementation_ready",
  "publication_fields_reviewed_missing",
  "publication_fields_requiring_review",
  "publication_review_progress_pct",
  "publication_implementation_evidence_pct",
  "toolkit_parameter_actions",
];
const matrixColumns = [
  ...matrixMetadataColumns,
  ...allParameters.map((parameter) => parameter.columnKey),
];
const studyIdentityColumns = [
  "study_row_id",
  "network_node_id",
  "record_id",
  "publication_id",
  "experiment_id",
  "paradigm_variant_id",
  "profile_id",
  "task_family",
];
const studyInstanceMetadataColumns = [
  "study_label",
  "experiment_letter",
  "experiment_label",
  "formal_experiment_number",
  "instance_kind",
  "instance_inventory_status",
  "toolkit_scope",
  "parameter_evidence_scope",
  "known_instance_count",
  "instance_count_basis",
  "instance_evidence_pointer",
  "experiment_disaggregation_status",
  "title",
  "year",
  "doi",
  "publication_url",
  "toolkit_status",
  "toolkit_join_status",
  "evidence_stage",
  "pdf_status",
  "supplement_status",
  "extraction_status",
  "manual_review_status",
  "orientation_review_status",
  "visualization_review_status",
  "visualization_candidate_count",
  "network_prominence_rank",
  "network_prominence",
  "atomic_parameter_count",
  "atomic_review_completed_count",
  "atomic_review_required_count",
  "parent_reviewed_missing_count",
  "parent_source_unknown_count",
  "new_parameters_not_in_current_audit_count",
];
const studyInstanceColumns = [
  ...studyIdentityColumns,
  ...studyInstanceMetadataColumns,
  ...PAPER_PARAMETERS.map((parameter) => parameter.parameterId),
];
const publicationAtomicMetadataColumns = [
  "network_node_id",
  "title",
  "year",
  "doi",
  "toolkit_status",
  "study_instance_count",
  "study_row_ids",
  "record_ids",
  "profile_ids",
  "network_prominence_rank",
];
const publicationAtomicColumns = [
  ...publicationAtomicMetadataColumns,
  ...PAPER_PARAMETERS.map((parameter) => parameter.parameterId),
];
const studyIndexColumns = Object.keys(studyIndexRows[0]);
const evidenceColumns = Object.keys(evidenceRows[0]);
const queueColumns = Object.keys(reviewQueueRows[0]);
const dictionaryColumns = Object.keys(dictionaryRows[0]);
const summaryColumns = Object.keys(summaryRows[0]);
const legendColumns = Object.keys(legendRows[0]);
const atomicEvidenceColumns = Object.keys(atomicEvidenceRows[0]);
const atomicQueueColumns = Object.keys(atomicReviewQueueRows[0]);
const orientationColumns = Object.keys(orientationRows[0]);
const fullDictionaryColumns = Object.keys(fullDictionaryRows[0]);
const targetCrosswalkColumns = Object.keys(targetCrosswalkRows[0]);
const currentInputReviewCrosswalkColumns = Object.keys(currentInputReviewCrosswalkRows[0]);
const currentInputReviewColumns = [
  "study_row_id",
  "network_node_id",
  "record_id",
  "study_label",
  "experiment_letter",
  "experiment_label",
  "parameter_evidence_scope",
  "toolkit_scope",
  "profile_ids",
  ...currentInputSchema.inputs.map((parameter) => parameter.serialized_path),
];
const publicationCurrentInputReviewColumns = [
  "network_node_id",
  "title",
  "year",
  "doi",
  "toolkit_status",
  "study_instance_count",
  "study_row_ids",
  ...currentInputSchema.inputs.map((parameter) => parameter.serialized_path),
];
const currentInputReviewQueueColumns = Object.keys(currentInputReviewQueueRows[0]);
const currentInputReviewLegendColumns = Object.keys(currentInputReviewLegendRows[0]);
const fullSummaryColumns = Object.keys(fullSummaryRows[0]);
const fullGroupSummaryColumns = Object.keys(fullGroupSummaryRows[0]);
const fullLegendColumns = Object.keys(fullLegendRows[0]);
const outsideAuditColumns = Object.keys(outsideAuditRows[0]);
const implementationSurfaceColumns = Object.keys(implementationSurfaceRows[0]);
const discrepancyColumns = Object.keys(discrepancyRows[0]);

const publicationStatusCounts = {};
for (const parameter of publicationParameters) {
  for (const row of matrixRows) {
    const status = row[parameter.columnKey];
    publicationStatusCounts[status] = (publicationStatusCounts[status] || 0) + 1;
  }
}
const toolkitStatusCounts = Object.fromEntries(
  Object.entries(
    matrixRows.reduce((counts, row) => {
      counts[row.toolkit_status] = (counts[row.toolkit_status] || 0) + 1;
      return counts;
    }, {}),
  ).sort(([left], [right]) => left.localeCompare(right)),
);
const reviewTierCounts = Object.fromEntries(
  ["P0", "P1", "P2", "P3"].map((tier) => [
    tier,
    reviewQueueRows.filter((row) => row.priority_tier === tier).length,
  ]),
);
const topPublicationGaps = summaryRows
  .filter((row) => row.layer === "publication_evidence")
  .sort(
    (left, right) =>
      right.action_required_count - left.action_required_count ||
      left.parameter_key.localeCompare(right.parameter_key),
  )
  .slice(0, 10);
const topStudies = [...matrixRows]
  .sort(
    (left, right) =>
      right.publication_fields_requiring_review - left.publication_fields_requiring_review ||
      right.publication_fields_reviewed_missing - left.publication_fields_reviewed_missing ||
      left.network_prominence_rank - right.network_prominence_rank,
  )
  .slice(0, 15);

const atomicStatusTotals = {};
for (const parameter of PAPER_PARAMETERS) {
  for (const row of studyInstanceRows) {
    const status = row[parameter.parameterId];
    atomicStatusTotals[status] = (atomicStatusTotals[status] || 0) + 1;
  }
}
const provisionalRoutingHintCounts = PAPER_PARAMETERS.reduce((counts, parameter) => {
  counts[parameter.provisionalRoutingHint] = (counts[parameter.provisionalRoutingHint] || 0) + 1;
  return counts;
}, {});
const currentDesignBindingCounts = PAPER_PARAMETERS.reduce((counts, parameter) => {
  const state = targetBindingById.get(parameter.parameterId).currentBindingState;
  counts[state] = (counts[state] || 0) + 1;
  return counts;
}, {});
const evidenceStageCounts = studyInstanceRows.reduce((counts, row) => {
  counts[row.evidence_stage] = (counts[row.evidence_stage] || 0) + 1;
  return counts;
}, {});
const structuredOrientationReviewRecords = manualReviews.filter(
  (review) => joinedNetworkRecordIds.has(review.record_id) && review.orientation_ledger,
).length;
const experimentSpecificOrientationRows = orientationRows.filter(
  (row) => row.orientation_review_status === "structured_orientation_review_present",
).length;
const combinedOrientationRows = orientationRows.filter(
  (row) => row.orientation_review_status === "combined_record_orientation_requires_experiment_check",
).length;
const automatedVisualizationCandidates = auditRecords
  .filter((record) => joinedNetworkRecordIds.has(record.record_id))
  .reduce(
    (sum, record) => sum + (record.pps_visualization_audit?.visualization_candidates || []).length,
    0,
  );
const studyVisualizationCandidateRows = visualizationRows.filter(
  (row) =>
    row.confirmation_status === "automated_candidate_unverified" ||
    row.confirmation_status === "record_level_candidate_requires_experiment_check",
).length;
const confirmedVisualizationRows = visualizationRows.filter(
  (row) => row.confirmation_status === "confirmed",
).length;
const publicationNodesWithAbstract = network.nodes.filter(
  (node) => String(node.abstract?.text || "").trim(),
).length;
const publicationNodesWithoutAbstractOrAudit = network.nodes.filter(
  (node) =>
    !String(node.abstract?.text || "").trim() &&
    !(node.toolkit?.records || []).length,
).length;
const multiExperimentPublications = publicationAtomicRows.filter(
  (row) => row.study_instance_count > 1,
);
const topAtomicRecoveryLoads = [...fullSummaryRows]
  .sort(
    (left, right) =>
      right.parent_reviewed_missing_count - left.parent_reviewed_missing_count ||
      right.source_unknown_count - left.source_unknown_count ||
      right.not_covered_by_current_audit_count - left.not_covered_by_current_audit_count ||
      left.target_parameter_path.localeCompare(right.target_parameter_path),
  )
  .slice(0, 15);
const structuralGapParameters = PAPER_PARAMETERS.filter(
  (parameter) => parameter.provisionalRoutingHint === "unsupported_structural_gap",
);

const markdown = `# Publication-to-Toolkit Input Review Matrix

Generated ${GENERATED_ON} from the tracked \`pps-publication-citation-network.v3\` asset, exact-DOI audit joins, manual-review overrides, current profile manifests, and the repository's code/schema surfaces.

The primary paper-review deliverable is a **${studyInstanceRows.length}-row × ${PARSIMONIOUS_CONTRACT_COUNT}-contract categorical matrix** aligned to Toolkit Segments 1-5 and runtime: auditory stimulus; trajectory geometry plus kinematics; trial sequence; task/response behavior; jitter/ITI; SOA schedule; tactile target; baseline trials; catch trials; repetition allocation; and block composition/order. Every one of the ${publicationAtomicRows.length} citation-network publications is represented, and a strict ${publicationAtomicRows.length}-row aggregate is supplied. The registered view has ${studyInstanceRows.length} rows because ${studyInstanceRegistry.entries.length} publications have tracked multi-experiment or multi-profile splits.

The exact **${studyInstanceRows.length}-row × ${currentInputSchema.input_count}-input** current design/profile matrices remain the implementation crosswalk. The broader **${studyInstanceRows.length}-row × ${PAPER_PARAMETERS.length}-leaf** target matrix remains a scientific-method and validation-gap inventory—not claims about fields accepted by the current serializer. Publications without a registry entry remain one review unit and are explicitly marked \`experiment_count_not_assessed\`; do not infer that they contain only one experiment. Only ${publicationNodesWithAbstract} of ${publicationAtomicRows.length} nodes have tracked abstract text, and ${publicationNodesWithoutAbstractOrAudit} have neither abstract text nor an exact-DOI audit record, so ${studyInstanceRows.length} is an evidence-backed review-row count rather than an exhaustive true experiment count.

The compact matrix reports whether contract-level evidence is complete, derived, partial, absent, unavailable, unassessed, or still composite. A reported or derived completion is component-gated: every required final component must have experiment-scoped evidence. The normalized evidence ledger preserves final component states, the underlying coarse-parent evidence, short paper value, source/page pointer, derivation note, exact current input paths, and any attached template encoding. It never promotes a coarse 25-field audit parent, template value, or Toolkit default to complete publication evidence. Controlled vocabularies distinguish generated/imported/physical sources, motion modes, timing policies, baseline trial families, catch target roles, and exact versus unresolved allocation rules. The 281-leaf atomic matrix remains stricter: each constituent target leaf still requires separate verification.

The builder overwrites the named files recorded in
\`generated_output_manifest.json\`; it removes only obsolete files named by a
prior manifest and leaves unrelated files alone. Before entering manual values,
copy the review queue/sidecar to a dated working CSV and promote accepted
annotations into a durable reviewed-data source before rebuilding.

## Primary Parsimonious Paper-Review Files

- \`study_instance_parsimonious_status_matrix.csv\`: the primary compact have/missing table—${studyInstanceRows.length} registered study rows × ${PARSIMONIOUS_CONTRACT_COUNT} scientific emulation contracts.
- \`study_instance_parsimonious_value_matrix.csv\`: the same rows with short extracted paper values; composite-record evidence is visibly prefixed and never presented as experiment-specific.
- \`publication_parsimonious_status_matrix.csv\`: strict ${publicationAtomicRows.length}-publication aggregate; differing child rows become \`mixed_across_studies\`.
- \`parsimonious_contract_evidence.csv\`: normalized study × contract ledger with value, source/page, final and coarse component states, derivation, current-path crosswalk, and template encoding.
- \`parsimonious_contract_review_queue.csv\`: prioritized unresolved, caveated, and derived contract decisions.
- \`parsimonious_contract_dictionary.csv\`, \`parsimonious_contract_summary.csv\`, and \`parsimonious_status_legend.csv\`: contract definitions, coverage counts, and status meanings.

Experiment-scoped values recovered from locally verified PDFs are stored as short tracked source reviews in \`parsimonious_source_reviews.v1.json\`; raw PDFs remain ignored and unredistributed.

The compact status matrix is intentionally categorical. Detailed values stay in the value matrix and evidence ledger so the paper-facing sheet remains small. Geometry and kinematics are one reconstructibility contract: a canonical 3D/body-relative path plus enough of duration, path length, and speed to derive the redundant quantity. Baseline and catch remain separate because a tactile-only or endpoint control is not equivalent to a no-target/withhold trial, and auditory-only response trials must not be mislabeled as catches. EEG/prestimulus analysis baselines are excluded from the trial-generation baseline contract.

## Current-Toolkit Implementation Crosswalk Files

- \`study_instance_current_input_review_matrix.csv\`: implementation-level evidence table—${studyInstanceRows.length} registered study/profile rows × ${currentInputSchema.input_count} exact current serialized input columns.
- \`publication_current_input_review_matrix.csv\`: the same evidence-review states aggregated to the ${publicationAtomicRows.length} citation-network publications.
- \`current_input_review_queue.csv\`: normalized long manual-review queue for all ${studyInstanceRows.length * currentInputSchema.input_count} current-input cells, including composite-evidence and untyped-object warnings.
- \`current_input_to_target_crosswalk.csv\`: inverse mapping from every exact current input to the proposed target leaves and coarse audit parents used to seed its review status.
- \`current_input_review_status_legend.csv\`: interpretation and required action for every current-evidence review category.
- \`study_instance_current_toolkit_input_matrix.csv\`: ${studyInstanceRows.length} registered study rows × ${currentInputSchema.input_count} exact inputs accepted by \`design_from_dict\` and emitted by \`design_to_dict\`.
- \`publication_current_toolkit_input_matrix.csv\`: the same current input paths aggregated to the ${publicationAtomicRows.length} publication nodes.
- \`current_toolkit_input_dictionary.csv\`: code-derived path, type, default, cardinality, parser, serializer, and source-line contract for every current input.
- \`current_toolkit_input_values.csv\`: normalized experiment/variant-scoped profile values by study, profile, and exact input path.
- \`publication_current_toolkit_input_values.csv\`: publication-scoped profile values, including composite profiles that are intentionally not assigned to individual experiment rows.
- \`current_toolkit_input_status_legend.csv\`: categorical encoding states used in the current matrices.

These implementation matrices describe the exact current **design/profile serialization** surface and what attached templates encode. They are not an inventory of every operational Toolkit namespace: capture, loudness, tactile calibration, adaptive tactile, top-up, latency validation, and analysis policies remain separately listed in \`implementation_surface_inventory.csv\`. They also do not by themselves prove that a value was reported by, or faithfully reconstructed from, a publication. Check \`publication_profile_scope\`: a \`composite_profile_not_experiment_scoped\` profile is visible only in the publication aggregate until its values are disaggregated.

## Secondary Target Method/Validation-Gap Files

- \`study_instance_target_method_validation_gap_matrix.csv\`: secondary ${studyInstanceRows.length}-row scientific method/validation inventory; multi-experiment papers are labeled \`(a)\`, \`(b)\`, \`(c)\`, and so on.
- \`publication_target_method_validation_gap_matrix.csv\`: strict ${publicationAtomicRows.length}-node target aggregate; \`mixed\` points back to differing study-instance rows.
- \`target_method_validation_dictionary.csv\`: all ${PAPER_PARAMETERS.length} proposed target method/validation paths, shapes, units, roles, repeating entities, coarse audit-parent mappings, and exact current-design crosswalk fields. Six leaves are explicitly validation/derived candidates rather than configuration inputs; older routing hints remain provisional.
- \`target_method_to_current_input_crosswalk.csv\`: conservative mapping from every proposed target leaf to exact current \`design.*\` paths, an untyped object container, a partial proxy/derived value, or \`not_in_current_design_serializer\`.
- \`study_instance_target_method_review_queue.csv\`: editable long target-review queue for every study/target pair, priority-sorted.
- \`study_instance_target_method_evidence_sidecar.csv\`: normalized target evidence/status ledger keyed by \`(study_row_id, target_parameter_path)\`.
- \`target_method_validation_parameter_summary.csv\` and \`target_method_validation_group_summary.csv\`: recovery load by proposed leaf/group.
- \`study_orientation_review.csv\`: one row per study instance with current structured orientation ledgers and empty visual-orientation verification fields.
- \`study_visualizations.csv\`: normalized one-to-many figure/table/panel review table; automated candidates are explicitly unconfirmed.
- \`target_method_validation_status_legend.csv\`: atomic-review, binding, and provisional routing-hint taxonomies.

## Supporting Files

- \`generated_output_manifest.json\`: exact managed file set for reproducibility and stale-artifact detection.
- \`study_instance_index.csv\` and \`publication_study_index.csv\`: human-readable row/publication metadata and exact joins.
- \`publication_parameter_matrix.csv\`: the current coarse ${publicationParameters.length}-field publication audit plus ${implementationParameters.length} profile inventory fields and ${gapParameters.length} generic gap fields. It is retained only as a migration baseline.
- \`publication_parameter_evidence_detail.csv\`, \`publication_parameter_dictionary.csv\`, \`publication_parameter_summary.csv\`, \`publication_parameter_review_queue.csv\`, and \`publication_parameter_status_legend.csv\`: current-schema evidence and gate diagnostics.
- \`implementation_surface_inventory.csv\`: separates current design inputs, other runtime/calibration namespaces, target leaves, and output-only schemas.
- \`implementation_discrepancies.csv\`: code/schema/documentation mismatches found during the inventory.
- \`audit_records_outside_network.csv\`: six audit records intentionally not joined to the focused 94-node display.

## Snapshot

| Measure | Count |
|---|---:|
| Focused publication nodes | ${publicationAtomicRows.length} |
| Citation links | ${network.edges.length} |
| Evidence-backed registered study/profile rows | ${studyInstanceRows.length} |
| Parsimonious paper-facing contract columns | ${PARSIMONIOUS_CONTRACT_COUNT} |
| Parsimonious study-contract evidence cells | ${studyInstanceRows.length * PARSIMONIOUS_CONTRACT_COUNT} |
| Exact current serialized Toolkit input columns | ${currentInputSchema.input_count} |
| Current-input categorical review cells | ${studyInstanceRows.length * currentInputSchema.input_count} |
| Proposed target method/validation columns | ${PAPER_PARAMETERS.length} |
| Target-review categorical cells | ${studyInstanceRows.length * PAPER_PARAMETERS.length} |
| Target leaves mapped to a current coarse audit parent | ${PAPER_PARAMETERS.filter((parameter) => parameter.currentAuditParents.length).length} |
| Target leaves absent from the current 25-field audit | ${PAPER_PARAMETERS.filter((parameter) => !parameter.currentAuditParents.length).length} |
| Exact current paths absent from the proposed target inventory | ${currentInputsOutsideTargetInventory.length} |
| Exact-DOI joined audit records | ${joinedNetworkRecordIds.size} |
| Publication nodes without an audit record | ${network.nodes.filter((node) => !(node.toolkit?.records || []).length).length} |
| Publication nodes with tracked abstract text | ${publicationNodesWithAbstract} |
| Publication nodes with neither abstract text nor an audit record | ${publicationNodesWithoutAbstractOrAudit} |
| Manual-review records joined to nodes | ${manualReviews.filter((review) => joinedNetworkRecordIds.has(review.record_id)).length} |
| Manual-review records with structured orientation ledgers | ${structuredOrientationReviewRecords} |
| Experiment-specific rows with a directly scoped orientation ledger | ${experimentSpecificOrientationRows} |
| Split rows inheriting a combined-record orientation ledger | ${combinedOrientationRows} |
| Automated visualization candidates needing visual verification | ${automatedVisualizationCandidates} |
| Study-level visualization candidate rows after experiment splitting | ${studyVisualizationCandidateRows} |
| Confirmed structured visualization rows | ${confirmedVisualizationRows} |
| Audit records outside focused network | ${outsideAuditRows.length} |

Toolkit publication states: ${Object.entries(toolkitStatusCounts)
  .map(([status, count]) => `\`${status}\` ${count}`)
  .join(", ")}.

Study-instance evidence stages: ${Object.entries(evidenceStageCounts)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([status, count]) => `\`${status}\` ${count}`)
  .join(", ")}.

## Multi-Experiment Publication Labels

| Publication | Study rows | Record/template identities |
|---|---:|---|
${multiExperimentPublications
  .map(
    (row) =>
      `| ${String(row.title).replaceAll("|", "\\|")} | ${row.study_instance_count} | ${row.study_row_ids.replaceAll("|", "\\|")} |`,
  )
  .join("\n")}

The suffix letters are review/display labels. Existing \`record_id\` and \`profile_id\` values are preserved unchanged.

## Proposed Target Method/Validation Groups

| Group | Namespace | Leaves | Coarse-parent mapped | New audit leaves | Structural gaps |
|---|---|---:|---:|---:|---:|
${fullGroupSummaryRows
  .map(
    (row) =>
      `| ${row.parameter_group} | \`${row.segment_or_namespace}\` | ${row.final_input_leaf_count} | ${row.leaves_with_current_audit_parent} | ${row.new_atomic_audit_leaves} | ${row.unsupported_structural_gap_count} |`,
  )
  .join("\n")}

## Atomic Review Status Totals

| Status | Cells |
|---|---:|
${Object.entries(atomicStatusTotals)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([status, count]) => `| \`${status}\` | ${count} |`)
  .join("\n")}

These totals distinguish four different kinds of unresolved work: no audit at all, unavailable/unextracted source evidence, a reviewed-but-missing coarse parent, and a brand-new atomic input not covered by the current audit.

## Largest Atomic Recovery Loads

| Proposed target method/validation leaf | Group | Reviewed-parent missing | Source unknown | Not in current audit | Provisional routing hint |
|---|---|---:|---:|---:|---|
${topAtomicRecoveryLoads
  .map(
    (row) =>
      `| \`${row.target_parameter_path}\` | ${row.parameter_group} | ${row.parent_reviewed_missing_count} | ${row.source_unknown_count} | ${row.not_covered_by_current_audit_count} | \`${row.provisional_implementation_hint}\` |`,
  )
  .join("\n")}

## Provisional Target Routing Hints

| Routing hint | Target method/validation leaves |
|---|---:|
${Object.entries(provisionalRoutingHintCounts)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([status, count]) => `| \`${status}\` | ${count} |`)
  .join("\n")}

The ${structuralGapParameters.length} explicitly identified structural gaps are:

${structuralGapParameters.map((parameter) => `- \`${parameter.parameterId}\``).join("\n")}

These legacy hints are only triage labels. They are not evidence that a target leaf is accepted, serialized, GUI-bound, or consumed by the current Toolkit; use the exact current-input dictionary and target crosswalk for implementation claims.

## Exact Current-Design Crosswalk

| Binding state | Proposed target leaves |
|---|---:|
${Object.entries(currentDesignBindingCounts)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([status, count]) => `| \`${status}\` | ${count} |`)
  .join("\n")}

This crosswalk is intentionally scoped to \`StimulusDesign\` serialization. Runtime, calibration, and analysis contracts remain in the implementation-surface inventory unless they have a versioned profile binding; absence from this crosswalk does not prove the concept is absent from every code path.

The proposed target inventory is also not a superset of the current serializer. These ${currentInputsOutsideTargetInventory.length} exact current paths have no target relation and therefore remain visible as \`not_covered_by_target_inventory\` in the primary current-input review matrix:

${currentInputsOutsideTargetInventory.map((row) => `- \`${row.current_toolkit_input_path}\``).join("\n")}

## Systematic Review Gaps

- Only ${structuredOrientationReviewRecords} of ${manualReviews.length} manual-review records contain the current structured orientation ledger. Of the registered rows, ${experimentSpecificOrientationRows} have an experiment-scoped ledger and ${combinedOrientationRows} inherit a combined-record ledger that still needs experiment-specific checking. The orientation worksheet therefore keeps participant frame, apparatus frame, body-relative mapping, tactile anchor, movement implementation, evidence class, and visual-vector verification separate.
- There are ${automatedVisualizationCandidates} automated visualization candidates in joined studies and **zero confirmed structured figure reviews**. Every candidate must be checked against the rendered figure/table/panel, axes, units, model, boundary/index definition, facets, and uncertainty display.
- ${PAPER_PARAMETERS.filter((parameter) => !parameter.currentAuditParents.length).length} proposed target method/validation leaves have no parent in the current 25-field extraction schema; these are not paper absences, just audit-schema gaps.
- \`source_unavailable\` is overloaded in automated records: it can mean no candidate was mined from an available source, not necessarily that the publication itself is unavailable. Use PDF, extraction, and manual-review stage columns together.

## Current Coarse Fields With The Largest Review Load

| Parent field | Segment | Actionable publications | Leading action |
|---|---:|---:|---|
${topPublicationGaps
  .map(
    (row) =>
      `| \`${row.parameter_key}\` | ${row.segment} | ${row.action_required_count} | \`${row.top_review_action}\` |`,
  )
  .join("\n")}

## Review Rules

1. Enter source values only in the long review/evidence ledger, keyed by \`study_row_id\` and proposed target parameter path. Keep the wide matrix categorical.
2. Never collapse \`not_assessed\`, \`source_unavailable\`, \`parent_reviewed_missing\`, and \`not_covered_by_current_audit\` into one blank.
3. Manual reviews override automated candidates. Never propagate values between related preprint/final-version DOIs without explicit version lineage.
4. Follow the retrieval ladder before closing a leaf as missing: main paper, figures/tables, supplement, publisher/fallback source, cited protocol lineage, then arithmetic/coordinate consistency.
5. For repeatable sources, trajectories, rows, blocks, parts, and instructions, store arrays/objects under the one target leaf rather than creating ad hoc columns.
6. A Toolkit support state is not evidence quality. Citation prominence is used only to order review work and is not a study-quality rating.
`;

await fs.mkdir(OUTPUT_DIR, { recursive: true });
try {
  const previousManifest = await loadJson(
    path.join(OUTPUT_DIR, GENERATED_OUTPUT_MANIFEST_FILENAME),
  );
  if (previousManifest.schema === "pps-publication-parameter-matrix-output.v1") {
    for (const filename of previousManifest.files || []) {
      if (
        typeof filename === "string" &&
        path.basename(filename) === filename &&
        !GENERATED_OUTPUT_FILENAMES.includes(filename)
      ) {
        await fs.rm(path.join(OUTPUT_DIR, filename), { force: true });
      }
    }
  }
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}
await Promise.all([
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_instance_current_input_review_matrix.csv"),
    toCsv(currentInputReviewRows, currentInputReviewColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "publication_current_input_review_matrix.csv"),
    toCsv(publicationCurrentInputReviewRows, publicationCurrentInputReviewColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "current_input_review_queue.csv"),
    toCsv(currentInputReviewQueueRows, currentInputReviewQueueColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "current_input_to_target_crosswalk.csv"),
    toCsv(currentInputReviewCrosswalkRows, currentInputReviewCrosswalkColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "current_input_review_status_legend.csv"),
    toCsv(currentInputReviewLegendRows, currentInputReviewLegendColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_instance_target_method_validation_gap_matrix.csv"),
    toCsv(studyInstanceRows, studyInstanceColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "publication_target_method_validation_gap_matrix.csv"),
    toCsv(publicationAtomicRows, publicationAtomicColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_instance_index.csv"),
    toCsv(studyInstanceRows, [...studyIdentityColumns, ...studyInstanceMetadataColumns]),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_instance_target_method_review_queue.csv"),
    toCsv(atomicReviewQueueRows, atomicQueueColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_instance_target_method_evidence_sidecar.csv"),
    toCsv(atomicEvidenceRows, atomicEvidenceColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "target_method_validation_dictionary.csv"),
    toCsv(fullDictionaryRows, fullDictionaryColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "target_method_to_current_input_crosswalk.csv"),
    toCsv(targetCrosswalkRows, targetCrosswalkColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "target_method_validation_parameter_summary.csv"),
    toCsv(fullSummaryRows, fullSummaryColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "target_method_validation_group_summary.csv"),
    toCsv(fullGroupSummaryRows, fullGroupSummaryColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_orientation_review.csv"),
    toCsv(orientationRows, orientationColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "study_visualizations.csv"),
    toCsv(visualizationRows, VISUALIZATION_COLUMNS),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "target_method_validation_status_legend.csv"),
    toCsv(fullLegendRows, fullLegendColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "implementation_surface_inventory.csv"),
    toCsv(implementationSurfaceRows, implementationSurfaceColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "implementation_discrepancies.csv"),
    toCsv(discrepancyRows, discrepancyColumns),
  ),
  fs.writeFile(
    path.join(OUTPUT_DIR, "audit_records_outside_network.csv"),
    toCsv(outsideAuditRows, outsideAuditColumns),
  ),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_parameter_matrix.csv"), toCsv(matrixRows, matrixColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_parameter_review_queue.csv"), toCsv(reviewQueueRows, queueColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_parameter_evidence_detail.csv"), toCsv(evidenceRows, evidenceColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_parameter_dictionary.csv"), toCsv(dictionaryRows, dictionaryColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_parameter_summary.csv"), toCsv(summaryRows, summaryColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_study_index.csv"), toCsv(studyIndexRows, studyIndexColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "publication_parameter_status_legend.csv"), toCsv(legendRows, legendColumns)),
  fs.writeFile(path.join(OUTPUT_DIR, "README.md"), markdown),
]);

const currentMatrixBuild = JSON.parse(
  execFileSync(
    PYTHON_EXECUTABLE,
    [
      CURRENT_INPUT_BUILDER_PATH,
      "--output",
      OUTPUT_DIR,
      "--schema-output",
      CURRENT_INPUT_SCHEMA_PATH,
    ],
    { cwd: REPO_ROOT, encoding: "utf8" },
  ),
);
const parsimoniousMatrixBuild = JSON.parse(
  execFileSync(
    PYTHON_EXECUTABLE,
    [PARSIMONIOUS_BUILDER_PATH, "--output", OUTPUT_DIR],
    { cwd: REPO_ROOT, encoding: "utf8" },
  ),
);
await fs.writeFile(
  path.join(OUTPUT_DIR, GENERATED_OUTPUT_MANIFEST_FILENAME),
  `${JSON.stringify(
    {
      schema: "pps-publication-parameter-matrix-output.v1",
      generated_on: GENERATED_ON,
      generator: "tools/build_publication_parameter_review_matrix.mjs",
      files: GENERATED_OUTPUT_FILENAMES,
    },
    null,
    2,
  )}\n`,
);

console.log(
  JSON.stringify(
    {
      generatedOn: GENERATED_ON,
      outputDir: path.relative(REPO_ROOT, OUTPUT_DIR),
      publications: matrixRows.length,
      networkEdges: network.edges.length,
      publicationParameters: publicationParameters.length,
      currentToolkitInputParameters: currentMatrixBuild.current_toolkit_input_count,
      parsimoniousContractCount: parsimoniousMatrixBuild.contract_count,
      parsimoniousReviewCells: parsimoniousMatrixBuild.evidence_cell_count,
      parsimoniousReviewQueueRows: parsimoniousMatrixBuild.review_queue_count,
      parsimoniousStatusCounts: parsimoniousMatrixBuild.status_counts,
      currentInputReviewCells: currentInputReviewQueueRows.length,
      currentInputsOutsideTargetInventory: currentInputsOutsideTargetInventory.length,
      targetMethodValidationParameters: PAPER_PARAMETERS.length,
      targetConfigurationCandidates: fullDictionaryRows.filter(
        (row) => row.parameter_role === "configuration_input",
      ).length,
      targetValidationLeaves: fullDictionaryRows.filter(
        (row) => row.parameter_role === "reported_or_target_validation_input",
      ).length,
      studyInstances: studyInstanceRows.length,
      targetMethodReviewCells: atomicEvidenceRows.length,
      publicationAtomicRows: publicationAtomicRows.length,
      structuredOrientationReviewRecords,
      experimentSpecificOrientationRows,
      combinedOrientationRows,
      automatedVisualizationCandidates,
      studyVisualizationCandidateRows,
      confirmedVisualizationRows,
      publicationNodesWithAbstract,
      publicationNodesWithoutAbstractOrAudit,
      outsideAuditRecords: outsideAuditRows.length,
      provisionalRoutingHintCounts,
      currentDesignBindingCounts,
      implementationParameters: implementationParameters.length,
      gapParameters: gapParameters.length,
      evidenceRows: evidenceRows.length,
      reviewQueueRows: reviewQueueRows.length,
      toolkitStatusCounts,
      reviewTierCounts,
      profileManifestCount: profileManifests.length,
      manualReviewCount: manualReviews.length,
      auditRecordCount: auditRecords.length,
      implementationStatusOrder: IMPLEMENTATION_STATUS_ORDER,
    },
    null,
    2,
  ),
);
