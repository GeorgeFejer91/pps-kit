let state = null;
let viewerReady = false;
const activePolls = new Set();
let activeNavFrame = 0;
const CUSTOM_TEMPLATE_ID = "__custom__";
const PROFILE_RECREATION_NOTICE =
  "Be aware: this is not the exact stimulus set used in the original study. This preload recreates the study's reported parameters within this interface, using the toolkit's local rendering and bundled profile assets.";
const WORKFLOW_STEPS = ["study", "stimulus", "trials", "baseline", "block", "schedule", "run"];
const STEP_TARGETS = {
  study: "study",
  stimulus: "stimulus",
  trials: "trials",
  baseline: "baseline",
  block: "block",
  schedule: "schedule",
  run: "run"
};
const NEXT_STEP = {
  study: "stimulus",
  stimulus: "trials",
  trials: "baseline",
  baseline: "block",
  block: "schedule",
  schedule: "run"
};
const STEP_SEGMENT_FOLDERS = {
  study: "0_profile",
  stimulus: "1_core_audio_ingredients",
  trials: "2_trial_sequence_designs",
  baseline: "3_tactile_and_baseline_trials",
  block: "4_trial_repetition_pool",
  schedule: "5_block_csv_preview",
  run: "6_experiment_run_setup"
};
const SEGMENT_INFO = {
  study: {
    kicker: "Segment 0",
    title: "Choose or Create Study",
    purpose: "Select a published profile or start a custom study.",
    inputs: "Study/profile preload and design name.",
    backend: "Creates or activates the 0_profile study project folder and writes profile/study manifests.",
    next: "Provides the active project context for every later segment."
  },
  stimulus: {
    kicker: "Segment 1",
    title: "Build Looming Stimuli",
    purpose: "Define the auditory ingredients available to the experiment.",
    inputs: "Trajectory values, generated noise type, custom tones, custom clips, bake label, gain.",
    backend: "Copies, imports, or bakes 1_core_audio_ingredients audio ingredients and records source metadata.",
    next: "Supplies stimulus ingredients for Trial Sequence Design."
  },
  trials: {
    kicker: "Segment 2",
    title: "Trial Sequence Design",
    purpose: "Arrange ingredients into within-trial audio sequences.",
    inputs: "Row/box order, fixed clips, looming sources, alternatives, jitter values.",
    backend: "Bakes 2_trial_sequence_designs row-level sequence WAVs and a manifest mapping each file to its components and timing.",
    next: "Feeds exact trial sequences into baseline/tactile trial generation."
  },
  baseline: {
    kicker: "Segment 3",
    title: "Baseline and Tactile Trial Design",
    purpose: "Add tactile timing and baseline/catch trial variants.",
    inputs: "SOAs, baseline strategy, custom baseline SOAs, catch trial choice.",
    backend: "Creates 3_tactile_and_baseline_trials three-channel target and baseline WAVs, optional catch WAVs, and row-preserving manifests.",
    next: "Supplies final trial files for repetition-pool construction."
  },
  block: {
    kicker: "Segment 4",
    title: "Trial Repetition Pool",
    purpose: "Decide how many times each trial family/file should appear.",
    inputs: "Global, folder, or file-level repetition counts.",
    backend: "Writes the 4_trial_repetition_pool CSV and manifest without duplicating WAV files.",
    next: "Provides the trial rows that will be arranged into blocks."
  },
  schedule: {
    kicker: "Segment 5",
    title: "Generate and Review Blocks",
    purpose: "Generate block CSVs and accept the final block set.",
    inputs: "Block count, regenerate/accept decision.",
    backend: "Creates 5_block_csv_preview block CSV previews, then finalizes accepted block CSVs.",
    next: "Unlocks experiment preparation and provides block order inputs."
  },
  run: {
    kicker: "Segment 6",
    title: "Prepare Experiment",
    purpose: "Set final experiment-level run parameters.",
    inputs: "Participant count, 1-part/2-part structure, preloaded instruction audio clips, and block-order sequence.",
    backend: "Writes the 6_experiment_run_setup participant block-order CSV/manifest, run instruction profile, and native runner session.",
    next: "Hands off to Focus Mode for timing-sensitive participant runs."
  }
};
const DOWNSTREAM_STEPS = {
  stimulus: ["trials", "baseline", "block", "schedule", "run"],
  trials: ["baseline", "block", "schedule", "run"],
  baseline: ["block", "schedule", "run"],
  block: ["schedule", "run"],
  schedule: ["run"],
  run: []
};
const LOCAL_BACKEND_DEFAULT = "http://127.0.0.1:8766";
const PANEL_RESIZE_SNAP_PX = 8;
const PANEL_HEIGHT_MIN = 150;
const PANEL_HEIGHT_MAX = 1000;
const SPLIT_DEFAULTS = {
  sideWidth: 460,
  ordersWidth: 420
};
const SPLIT_LIMITS = {
  sideWidth: { min: 320, max: 760 },
  ordersWidth: { min: 300, max: 760 }
};
const PROCEDURAL_NOISE_TYPES = [
  { value: "white", label: "White" },
  { value: "pink", label: "Pink" },
  { value: "blue", label: "Blue" },
  { value: "violet", label: "Violet" },
  { value: "brown", label: "Brown" }
];
const STIMULUS_TRAJECTORY_COLORS = {
  pink: "#d783b5",
  blue: "#4b7fc4",
  white: "#d8dde2",
  brown: "#8b623f",
  violet: "#8364b9",
  custom_audio: "#246b55",
  preserve: "#246b55",
  spatialize: "#246b55",
  prestimulus: "#7b8288"
};
const SOURCE_COLOR_OPTIONS = [
  { value: "pink", label: "Pink" },
  { value: "blue", label: "Blue" },
  { value: "white", label: "White" },
  { value: "brown", label: "Brown" },
  { value: "violet", label: "Violet" },
  { value: "custom_audio", label: "Green / custom" }
];
const TRIAL_FAMILY_COLORS = {
  audio_tactile: "#246b55",
  baseline: "#4b5fa8",
  catch: "#a4631b"
};
const RUN_INSTRUCTION_SLOTS = [
  { slot: "before_experiment", label: "Before experiment" },
  { slot: "before_each_block", label: "Before each block" },
  { slot: "after_each_block", label: "After each block" },
  { slot: "between_conditions", label: "Between conditions" },
  { slot: "after_experiment", label: "After experiment" }
];
const RUN_INSTRUCTION_CONTINUE_MODES = [
  { value: "click", label: "Click target" },
  { value: "delay", label: "Timed delay" },
  { value: "button", label: "Runner button" }
];
const IMPORTED_AUDIO_HANDLING = [
  { value: "spatialize", label: "Custom looming tone" },
  { value: "preserve", label: "Custom audio clip" }
];
const STIMULUS_SNIPPET_PLACEMENTS = [
  { value: "before", label: "Before stimulus" },
  { value: "after", label: "After stimulus" }
];
const BASELINE_STRATEGY_NOTES = {
  "": {
    label: "Baseline decision required",
    note: "Choose the baseline family before preparing a custom run."
  },
  none: {
    label: "No baseline trials",
    note: "Only audio-tactile trial files are baked from the trial-sequence variants."
  },
  min_anchor: {
    label: "Minimum SOA anchor",
    note: "The full trial audio is preserved and tactile is added at the first entered SOA."
  },
  max_anchor: {
    label: "Maximum SOA anchor",
    note: "The full trial audio is preserved and tactile is added at the last entered SOA."
  },
  tactile_only: {
    label: "Full SOA tactile-only",
    note: "Fixed clips and jitter are preserved, looming segments are silenced, and tactile is added at every SOA."
  },
  min_max: {
    label: "Minimum + maximum SOA anchors",
    note: "The full trial audio is preserved and tactile is added at the first and last entered SOA."
  },
  soa_zero: {
    label: "Single anchor: sound onset",
    note: "Baseline tactile cues occur at auditory onset, giving a synchronous/minimum-timing anchor."
  },
  sound_offset: {
    label: "Single anchor: sound offset",
    note: "Baseline tactile cues occur at the end of the sound window, giving a late/maximum-timing anchor."
  },
  custom: {
    label: "Custom timings",
    note: "Custom baseline timings use the entered SOAs and the selected tactile-only/audio-tactile mode."
  }
};
const TRAJECTORY_FIELD_IDS = [
  "start-distance",
  "end-distance",
  "start-rotation",
  "end-rotation",
  "movement-duration",
  "start-hold",
  "end-hold"
];
const TRIAL_PREVIEW_LIMIT = 240;

const $ = (id) => document.getElementById(id);
const cssEscape = (value) => (window.CSS && window.CSS.escape ? window.CSS.escape(String(value)) : String(value).replace(/["\\]/g, "\\$&"));
let apiBase = "";
let templateLoadInFlight = false;
let pendingAudioImportMode = "preserve";
let pendingInstructionSlot = "";
let pendingBakeRecipe = null;
let activeTrialRowPreviewAudio = null;
let activeSourcePreviewAudio = null;
let activeSourcePreviewNode = null;
let activeSourcePreviewButton = null;
let activeSourcePreviewClearTimer = null;
let sourcePreviewAudioContext = null;
let customizeModalReturnFocus = null;
let segmentInfoModalReturnFocus = null;
let trialPoolRepetitionDraft = {
  defaultRepetitions: 1,
  familyRepetitions: {},
  folderRepetitions: {},
  fileRepetitionOverrides: {},
  fractionalSeed: 20250604
};
let trialPoolDraftSourceHash = "";
let trialPoolDraftInitialized = false;
let runSequencePreviewTimer = null;
let activePage = "toolkit";
const PAGE_TABS = ["toolkit", "documentation", "downloads"];
const PAGE_ROUTE_ALIASES = {
  "": "toolkit",
  toolkit: "toolkit",
  app: "toolkit",
  documentation: "documentation",
  docs: "documentation",
  download: "downloads",
  downloads: "downloads"
};
const PAGE_ROUTE_SEGMENTS = {
  toolkit: "",
  documentation: "documentation",
  downloads: "download"
};

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      headers: { "Content-Type": "application/json" },
      ...options
    });
  } catch (error) {
    setConnectionStatus(false);
    throw error;
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const raw = await response.text();
      const data = raw ? JSON.parse(raw) : {};
      detail = data.detail || detail;
    } catch (_err) {
      // Keep the status line when the response is not JSON, such as a static-site 404.
    }
    // HTTP errors still mean the companion answered; only fetch failures are disconnected.
    setConnectionStatus(true);
    throw new Error(detail);
  }
  setConnectionStatus(true);
  return response.json();
}

function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBase}${path}`;
}

function isLocalDashboardOrigin() {
  return ["127.0.0.1", "localhost", "[::1]", "::1"].includes(window.location.hostname);
}

function isCompanionDashboardOrigin() {
  return isLocalDashboardOrigin() && window.location.pathname.replace(/\\/g, "/").startsWith("/dashboard/");
}

function loadApiBase() {
  const stored = localStorage.getItem("ppsDashboard.apiBase");
  apiBase = stored || (isCompanionDashboardOrigin() ? "" : LOCAL_BACKEND_DEFAULT);
  $("backend-url").value = apiBase || (isCompanionDashboardOrigin() ? window.location.origin : LOCAL_BACKEND_DEFAULT);
}

function saveApiBase(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  const companionOrigin = isCompanionDashboardOrigin();
  apiBase = trimmed && !(companionOrigin && trimmed === window.location.origin) ? trimmed : "";
  if (apiBase) {
    localStorage.setItem("ppsDashboard.apiBase", apiBase);
  } else {
    localStorage.removeItem("ppsDashboard.apiBase");
  }
  $("backend-url").value = apiBase || (companionOrigin ? window.location.origin : LOCAL_BACKEND_DEFAULT);
}

function setConnectionStatus(connected) {
  const status = $("connection-status");
  if (!status) return;
  status.textContent = connected ? "connected" : "disconnected";
  status.className = `status-label ${connected ? "ready" : "required"}`;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function isCustomMode() {
  return Boolean(state?.custom_workflow?.is_custom);
}

function isProfileReadonlyMode() {
  return Boolean(state && !isCustomMode());
}

function ensureEditableProject() {
  if (!isProfileReadonlyMode()) return true;
  openCustomizeModal();
  showToast("Name a new custom study before editing this profile.");
  return false;
}

function setWorkflowDisabled(control, disabled) {
  if (!control) return;
  if (disabled) {
    if (!control.disabled) {
      control.dataset.workflowLockDisabled = "true";
    }
    control.disabled = true;
    return;
  }
  if (control.dataset.workflowLockDisabled === "true") {
    control.disabled = false;
    delete control.dataset.workflowLockDisabled;
  }
}

function profileReadonlyControlAllowed(control) {
  if (!control) return false;
  if (control.matches?.("[data-preview-source-label]")) return true;
  return Boolean(
    control.id
    && (control.id.startsWith("open-") || control.id === "prepare-experiment")
  );
}

function profileStepStatus(stepId) {
  const segment = projectSegment(STEP_SEGMENT_FOLDERS[stepId]);
  const label = getWorkflowStep(stepId)?.label || humanize(stepId);
  let complete = segment.status === "ready";
  if (stepId === "schedule") {
    complete = segment.status === "ready" && Boolean(segment.accepted || state.block_csv_preview?.accepted);
  }
  const message = segment.last_validation_message || segment.message || `${label} is not ready.`;
  return {
    id: stepId,
    label,
    complete,
    missing: complete ? [] : [message]
  };
}

function segmentHasMaterializedOutput(stepId) {
  const segment = projectSegment(STEP_SEGMENT_FOLDERS[stepId]);
  if (!segment || !Object.keys(segment).length) return false;
  return Boolean(
    segment.status === "ready"
    || segment.status === "stale"
    || segment.status === "preview"
    || segment.manifest_exists
    || segment.csv_exists
    || segment.wav_count
    || segment.file_count
    || segment.total_count
    || segment.block_count
    || segment.accepted
  );
}

function confirmDownstreamInvalidation(actionLabel, fromStep) {
  if (!isCustomMode()) return true;
  const affected = (DOWNSTREAM_STEPS[fromStep] || []).filter(segmentHasMaterializedOutput);
  if (!affected.length) return true;
  const labels = affected.map((step) => getWorkflowStep(step)?.label || humanize(step));
  return window.confirm(`${actionLabel} will invalidate downstream segment outputs: ${labels.join(", ")}. Continue?`);
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

function numberValue(id, fallback = 0) {
  const value = Number($(id).value);
  return Number.isFinite(value) ? value : fallback;
}

function parseIntegerList(value) {
  const seen = new Set();
  return String(value || "")
    .split(/[,\s;]+/)
    .map((item) => Number.parseInt(item.trim(), 10))
    .filter((item) => {
      if (!Number.isFinite(item) || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function parseNumberList(value) {
  return String(value || "")
    .split(",")
    .map((item) => Number.parseFloat(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function formatList(items) {
  return (items || []).join(", ");
}

async function loadState() {
  try {
    state = await api("/api/state");
    renderAll();
    updateViewer();
  } catch (error) {
    reportError(error);
  }
}

function renderAll() {
  if (!state) return;
  renderHeader();
  renderPageTabs();
  renderProfileMode();
  renderStudy();
  renderStimulus();
  renderTrials();
  renderBaseline();
  renderBlockCsvPreview();
  renderRun();
  renderPreviewTables();
  renderSegmentRegistryOutputs();
  renderWorkflow();
}

function normalizePageRoute(value) {
  const token = String(value || "")
    .trim()
    .replace(/^#/, "")
    .replace(/^\/+|\/+$/g, "")
    .toLowerCase();
  return PAGE_ROUTE_ALIASES[token] || "";
}

function topLevelLocation() {
  try {
    if (window.parent && window.parent !== window && window.parent.location.origin === window.location.origin) {
      return window.parent.location;
    }
  } catch (_err) {
    // Cross-origin parents cannot be inspected; direct dashboard routing remains local.
  }
  return window.location;
}

function topLevelHistory() {
  try {
    if (window.parent && window.parent !== window && window.parent.location.origin === window.location.origin) {
      return window.parent.history;
    }
  } catch (_err) {
    // Keep using the iframe/window history when parent access is not available.
  }
  return window.history;
}

function topLevelHash() {
  return topLevelLocation().hash || window.location.hash || "";
}

function pageFromPath(pathname) {
  const parts = String(pathname || "").replace(/\/+$/g, "").split("/").filter(Boolean);
  const last = parts[parts.length - 1] || "";
  if (last.toLowerCase() === "index.html") {
    return normalizePageRoute(parts[parts.length - 2] || "");
  }
  return normalizePageRoute(last);
}

function pageFromHash(hashValue = topLevelHash()) {
  const hash = String(hashValue || "").replace(/^#/, "");
  const pageHash = normalizePageRoute(hash);
  if (pageHash) return pageHash;
  const target = hash ? $(hash) : null;
  const panel = target?.closest("[data-page-panel]");
  const page = panel?.dataset.pagePanel || "";
  return PAGE_TABS.includes(page) ? page : "";
}

function pageFromLocation() {
  const queryPage = normalizePageRoute(new URLSearchParams(window.location.search).get("page"));
  if (queryPage) return queryPage;
  const routePage = pageFromPath(topLevelLocation().pathname);
  if (routePage) return routePage;
  return pageFromHash();
}

function publicRouteNavigationAvailable() {
  const location = topLevelLocation();
  if (!/^https?:$/i.test(location.protocol)) return false;
  return window.parent && window.parent !== window && location.origin === window.location.origin;
}

function publicRouteBasePath() {
  let path = String(topLevelLocation().pathname || "/")
    .replace(/\/index\.html$/i, "/")
    .replace(/\/(documentation|download|downloads)\/?$/i, "/");
  if (!path.endsWith("/")) path += "/";
  return path;
}

function pageRouteUrl(page, sectionId = "") {
  const nextPage = PAGE_TABS.includes(page) ? page : "toolkit";
  const cleanSection = String(sectionId || "").replace(/^#/, "");
  if (!publicRouteNavigationAvailable()) {
    const hash = cleanSection || (nextPage === "toolkit" ? "" : nextPage);
    return `${window.location.pathname}${window.location.search}${hash ? `#${hash}` : ""}`;
  }
  const base = publicRouteBasePath();
  const segment = PAGE_ROUTE_SEGMENTS[nextPage] || "";
  const routePath = segment ? `${base}${segment}` : base;
  return `${routePath}${cleanSection ? `#${cleanSection}` : ""}`;
}

function replaceRouteForPage(page, sectionId = "") {
  const url = pageRouteUrl(page, sectionId);
  try {
    topLevelHistory().replaceState(null, "", url);
  } catch (_err) {
    window.history.replaceState(null, "", url);
  }
}

function setActivePage(page, options = {}) {
  const nextPage = PAGE_TABS.includes(page) ? page : "toolkit";
  activePage = nextPage;
  document.body.dataset.activePage = nextPage;
  document.body.classList.toggle("info-page-active", nextPage !== "toolkit");
  for (const button of document.querySelectorAll("[data-page-tab]")) {
    const active = button.dataset.pageTab === nextPage;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  }
  for (const panel of document.querySelectorAll("[data-page-panel]")) {
    panel.hidden = panel.dataset.pagePanel !== nextPage;
    panel.classList.toggle("active", panel.dataset.pagePanel === nextPage);
  }
  syncRailForPage(nextPage);
  if (options.updateHash) {
    replaceRouteForPage(nextPage);
  }
  if (options.scrollTop) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  updateActiveNav();
  if (options.scrollTop && nextPage !== "toolkit") {
    const firstPageLink = document.querySelector(`[data-page-section-page="${cssEscape(nextPage)}"]`);
    setActivePageSection(firstPageLink?.dataset.pageSectionLink || "");
  }
}

function syncRailForPage(page) {
  for (const group of document.querySelectorAll("[data-rail-page]")) {
    const active = group.dataset.railPage === page;
    group.hidden = !active;
    group.classList.toggle("active", active);
  }
}

function setActivePageSection(sectionId) {
  if (!sectionId) return;
  for (const link of document.querySelectorAll("[data-page-section-link]")) {
    link.classList.toggle(
      "active",
      link.dataset.pageSectionPage === activePage && link.dataset.pageSectionLink === sectionId
    );
  }
}

function scrollToHashTarget() {
  const hash = String(topLevelHash() || "").replace(/^#/, "");
  if (!hash || PAGE_TABS.includes(hash)) return;
  const target = $(hash);
  if (!target) return;
  setActivePageSection(hash);
  window.requestAnimationFrame(() => {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => setActivePageSection(hash), 350);
  });
}

function renderPageTabs() {
  setActivePage(activePage);
}

function initializePageTabs() {
  setActivePage(pageFromLocation() || "toolkit");
  scrollToHashTarget();
}

function renderHeader() {
  $("design-title").textContent = state.design.name || "Untitled PPS design";
  const applyButton = $("apply-design");
  if (applyButton) {
    const readonly = isProfileReadonlyMode();
    applyButton.textContent = readonly ? "Profile Read-Only" : "Save Custom Design";
    applyButton.title = readonly
      ? "Create a custom project before editing this loaded profile."
      : "Save the current custom project decisions.";
    applyButton.disabled = readonly;
  }
}

function renderProfileMode() {
  const status = $("profile-mode-status");
  const button = $("edit-profile-rail");
  if (!status || !button) return;
  const readonly = isProfileReadonlyMode();
  status.textContent = readonly ? "profile run mode" : "custom edit mode";
  status.className = `status-label ${readonly ? "required" : "ready"}`;
  button.textContent = readonly ? "Edit As New Study" : "Editing Custom Study";
  button.disabled = !readonly;
  button.title = readonly
    ? "Create a named custom copy before changing this loaded profile."
    : "This project is already editable.";
}

function renderStudy() {
  const select = $("template-select");
  select.innerHTML = "";
  const customOption = document.createElement("option");
  customOption.value = CUSTOM_TEMPLATE_ID;
  customOption.textContent = "Custom design (define manually)";
  customOption.selected = !state.selected_template;
  select.appendChild(customOption);
  for (const template of state.templates) {
    const option = document.createElement("option");
    option.value = template.template_id;
    option.textContent = template.citation_label;
    option.selected = template.template_id === state.selected_template;
    select.appendChild(option);
  }
  $("design-name").value = state.design.name || "";
  const readonly = isProfileReadonlyMode();
  const applyProject = $("apply-profile-project");
  if (applyProject) {
    applyProject.hidden = readonly;
    applyProject.textContent = isCustomMode() ? "Create / Update Custom Project Folder" : "Apply Profile / Create Project Folder";
  }
  renderExistingCustomProjects();
  renderProfileSummary();
  renderPreloadAssetStatus();
}

function renderExistingCustomProjects() {
  const select = $("existing-custom-project");
  const button = $("load-custom-project");
  if (!select || !button) return;
  const projects = state.custom_projects || [];
  const activeProjectId = state.project?.project_kind === "custom" ? state.project.project_id : "";
  select.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = projects.length ? "Choose a saved custom study" : "No saved custom studies";
  select.appendChild(placeholder);
  for (const project of projects) {
    const option = document.createElement("option");
    option.value = project.project_id;
    option.textContent = project.created_at
      ? `${project.project_label} (${project.created_at})`
      : project.project_label;
    option.selected = project.project_id === activeProjectId;
    select.appendChild(option);
  }
  if (activeProjectId && [...select.options].some((option) => option.value === activeProjectId)) {
    select.value = activeProjectId;
  }
  button.disabled = !select.value;
  button.title = projects.length
    ? "Open a custom study already saved in the local dashboard project registry."
    : "No custom studies have been saved in the local dashboard project registry yet.";
}

function renderProfileSummary() {
  const selectedId = $("template-select").value;
  const current = state.templates.find((item) => item.template_id === selectedId);
  const href = current?.doi ? doiUrl(current.doi) : "";
  const summary = $("profile-summary");
  summary.hidden = !href;
  summary.innerHTML = href
    ? `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(href)}</a>`
    : "";
  const notice = $("profile-recreation-notice");
  if (notice) {
    const showNotice = Boolean(href && selectedId && selectedId !== CUSTOM_TEMPLATE_ID);
    notice.hidden = !showNotice;
    notice.textContent = showNotice ? PROFILE_RECREATION_NOTICE : "";
  }
}

function renderPreloadAssetStatus() {
  const badge = $("preload-asset-status");
  if (!badge) return;
  const selectedId = $("template-select").value;
  if (!selectedId || selectedId === CUSTOM_TEMPLATE_ID) {
    badge.hidden = true;
    return;
  }
  const current = state.templates.find((item) => item.template_id === selectedId);
  const status = current?.preload_asset_status || state.preload_inventory || {};
  const value = status.status || "not_indexed";
  const ready = Boolean(status.ready);
  badge.hidden = false;
  badge.textContent = ready
    ? `${status.ready_asset_count || status.asset_count || 0} local assets`
    : value === "recipe_only"
      ? "recipe only"
      : value.replace(/_/g, " ");
  badge.className = `status-label ${ready ? "ready" : value === "recipe_only" ? "" : "required"}`;
  badge.title = status.message || "";
}

function renderStimulus() {
  const controls = state.trajectory_controls || {};
  $("start-distance").value = controls.start_distance_cm ?? 110;
  $("end-distance").value = controls.end_distance_cm ?? 10;
  $("start-rotation").value = controls.start_rotation_deg ?? 0;
  $("end-rotation").value = controls.end_rotation_deg ?? 0;
  $("movement-duration").value = controls.movement_duration_s ?? 3;
  $("start-hold").value = controls.start_hold_s ?? 0.5;
  $("end-hold").value = controls.end_hold_s ?? 0.5;
  syncPreviewModeControls($("preview-mode").value || "2d");
  renderGeneratedNoiseSelect();
  renderBakePanel();
  renderNoiseTable();
  renderAudioTable();
  refreshAssemblyTargetOptions();
  renderSourceCounts();
}

function renderGeneratedNoiseSelect() {
  const select = $("generated-noise-select");
  const current = select.value;
  select.innerHTML = '<option value="">Choose noise type to bake...</option>';
  for (const item of PROCEDURAL_NOISE_TYPES) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  }
  select.value = PROCEDURAL_NOISE_TYPES.some((item) => item.value === current) ? current : "";
}

function renderBakePanel() {
  const status = $("bake-status");
  const button = $("bake-stimulus");
  if (!status || !button) return;
  if (!pendingBakeRecipe) {
    status.textContent = "No source staged";
    status.className = "status-label required";
    button.disabled = true;
    return;
  }
  const label = pendingBakeRecipe.label || pendingBakeRecipe.audio?.label || noiseTypeLabel(pendingBakeRecipe.noise_type);
  $("bake-label").value = label || "";
  $("bake-gain").value = Number(pendingBakeRecipe.gain || pendingBakeRecipe.audio?.gain || 1);
  const kind = pendingBakeRecipe.kind === "imported_audio" ? audioRoleTitle(pendingBakeRecipe.render_mode) : `${noiseTypeLabel(pendingBakeRecipe.noise_type)} noise`;
  status.textContent = `Staged: ${kind}`;
  status.className = "status-label ready";
  button.disabled = false;
}

function renderNoiseTable() {
  const list = $("noise-list");
  list.innerHTML = "";
  for (const noise of state.design.noises || []) {
    const selectedNoise = String(noise.noise_type || "pink").toLowerCase();
    const wav = renderedWavForLabel(noise.label || `${noiseTypeLabel(selectedNoise)} noise`);
    const localPath = noise.prebaked_path || wav?.path || "";
    const card = document.createElement("div");
    card.className = "source-card noise-source-card";
    applySourceCardColor(card, selectedNoise);
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(noiseTypeLabel(selectedNoise))} noise</strong>
        <div class="source-card-actions">
          ${sourceFolderAction(localPath)}
          <button type="button" data-remove-noise>Remove</button>
        </div>
      </div>
      ${stimulusTrajectoryHiddenFields(noise, selectedNoise, "generated_noise")}
      <input data-field="prebaked_path" type="hidden" value="${escapeAttr(localPath)}">
      <div class="source-card-fields">
        <div class="field-row">
          <label>Label</label>
          <input data-field="label" value="${escapeAttr(noise.label || "")}">
        </div>
        <div class="field-row">
          <label>Noise color</label>
          <select data-field="noise_type">
          ${PROCEDURAL_NOISE_TYPES.map((item) => `<option value="${item.value}" ${item.value === selectedNoise ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </div>
        <div class="field-row">
          <label>Azimuth</label>
          <input data-field="azimuth_deg" type="number" step="1" value="${Number(noise.azimuth_deg || 0)}">
        </div>
        <div class="field-row">
          <label>Elevation</label>
          <input data-field="elevation_deg" type="number" step="1" value="${Number(noise.elevation_deg || 0)}">
        </div>
        <div class="field-row">
          <label>Gain</label>
          <input data-field="gain" type="number" step="0.05" min="0.01" value="${Number(noise.gain || 1)}">
        </div>
      </div>
    `;
    list.appendChild(card);
  }
}

function renderAudioTable() {
  const list = $("audio-list");
  const snippetList = $("snippet-list");
  list.innerHTML = "";
  snippetList.innerHTML = "";
  const customFiles = state.design.custom_looming_files || [];
  const snippets = state.design.prestimulus_files || [];
  const rows = [
    ...customFiles.map((item) => ({
      ...item,
      audio_role: item.render_mode || "preserve",
      target_list: list,
    })),
    ...snippets.map((item) => ({
      ...item,
      audio_role: "prestimulus",
      target_list: list,
    }))
  ];
  for (const audio of rows) {
    const role = String(audio.audio_role || audio.use || audio.render_mode || "preserve").toLowerCase();
    const phase = audio.phase || "";
    const colorKey = role === "prestimulus" ? "prestimulus" : (audio.tone_type || audio.noise_type || "custom_audio");
    const motionMode = String(audio.motion_mode || (role === "prestimulus" ? "stationary" : "looming")).toLowerCase();
    const card = document.createElement("div");
    card.className = "source-card audio-source-card";
    card.dataset.audioRole = role;
    applySourceCardColor(card, colorKey);
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(audioRoleTitle(role))}</strong>
        <div class="source-card-actions">
          ${sourceFolderAction(audio.path)}
          <button type="button" data-remove-audio>Remove</button>
        </div>
      </div>
      ${stimulusTrajectoryHiddenFields(audio, colorKey, role === "prestimulus" ? "fixed_audio" : "imported_audio")}
      <input data-field="path" type="hidden" value="${escapeAttr(audio.path || "")}">
      <input data-field="motion_mode" type="hidden" value="${escapeAttr(motionMode)}">
      ${role === "prestimulus" ? `<input data-field="audio_role" type="hidden" value="prestimulus">` : ""}
      ${role === "prestimulus" ? `<input data-field="tone_type" type="hidden" value="${escapeAttr(colorKey)}">` : ""}
      <input data-field="placement" type="hidden" value="before">
      <input data-field="target_source_label" type="hidden" value="">
      <input data-field="phase" type="hidden" value="${escapeAttr(phase)}">
      <input data-field="gap_s" type="hidden" value="0">
      <div class="source-card-fields audio-source-fields">
        ${role === "prestimulus" ? "" : `
        <div class="field-row">
          <label>Source handling</label>
          <select data-field="audio_role">
            ${IMPORTED_AUDIO_HANDLING.map((item) => `<option value="${item.value}" ${item.value === role ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </div>
        `}
        ${role === "prestimulus" ? "" : `
        <div class="field-row source-color-field">
          <label>Box color</label>
          <select data-field="tone_type">
            ${sourceColorOptions(colorKey)}
          </select>
        </div>
        `}
        <div class="field-row">
          <label>Label</label>
          <input data-field="label" value="${escapeAttr(audio.label || "")}">
        </div>
        <div class="field-row">
          <label>Target s</label>
          <input data-field="target_duration_s" type="number" min="0.1" step="0.1" value="${Number(audio.target_duration_s || 4)}">
        </div>
        <div class="field-row">
          <label>Gain</label>
          <input data-field="gain" type="number" min="0.01" step="0.05" value="${Number(audio.gain || 1)}">
        </div>
      </div>
    `;
    audio.target_list.appendChild(card);
  }
}

function stimulusTrajectoryHiddenFields(source, colorKey = "custom_audio", sourceKind = "") {
  const snapshot = trajectorySnapshotForSource(source, colorKey, sourceKind);
  const rawValue = escapeAttr(JSON.stringify(snapshot || {}));
  return `<input data-field="trajectory_snapshot" type="hidden" value="${rawValue}">`;
}

function stimulusTrajectoryTrace(source, colorKey = "custom_audio", sourceKind = "") {
  const snapshot = trajectorySnapshotForSource(source, colorKey, sourceKind);
  const rawValue = escapeAttr(JSON.stringify(snapshot || {}));
  if (!snapshot || sourceKind === "fixed_audio") return `<input data-field="trajectory_snapshot" type="hidden" value="${rawValue}">`;
  const colors = trajectoryColorSet(snapshot, colorKey);
  const color = colors[0] || sourceColor(colorKey);
  const gradient = trajectoryGradient(colors);
  const start = Number(snapshot.start_distance_cm || 0);
  const end = Number(snapshot.end_distance_cm || 0);
  const startRot = Number(snapshot.start_rotation_deg || 0);
  const endRot = Number(snapshot.end_rotation_deg || 0);
  const duration = Number(snapshot.movement_duration_s || 0);
  const holdStart = Number(snapshot.start_hold_s || 0);
  const holdEnd = Number(snapshot.end_hold_s || 0);
  const path = Number(snapshot.path_length_m || Math.abs(start - end) / 100);
  const title = `${start || "?"} -> ${end || "?"} cm`;
  const detail = `${startRot} -> ${endRot} deg, ${duration}s move`;
  const shared = colors.length > 1 ? `shared path, ${colors.length} tones` : "";
  return `
    <div class="stimulus-trajectory-trace" style="--trajectory-color: ${escapeAttr(color)}; --trajectory-gradient: ${escapeAttr(gradient)}">
      <input data-field="trajectory_snapshot" type="hidden" value="${rawValue}">
      <div class="stimulus-trajectory-line" aria-hidden="true">
        <span class="trajectory-dot start"></span>
        <span class="trajectory-dot end"></span>
      </div>
      <div class="stimulus-trajectory-text">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(detail)}</span>
        <span>${escapeHtml(`${path.toFixed(2)} m path, holds ${holdStart}s/${holdEnd}s`)}</span>
        ${shared ? `<span>${escapeHtml(shared)}</span>` : ""}
      </div>
    </div>
  `;
}

function trajectoryColorSet(snapshot, fallbackKey = "custom_audio") {
  const fallback = sourceColor(fallbackKey);
  const groupKey = trajectoryGroupKey(snapshot);
  if (!groupKey || !state?.design) return [fallback];
  const colors = [];
  for (const source of stimulusInventorySources()) {
    const sourceSnapshot = trajectorySnapshotForSource(source, source.color_key, source.source_kind);
    if (trajectoryGroupKey(sourceSnapshot) !== groupKey) continue;
    const color = sourceColor(source.color_key);
    if (!colors.includes(color)) colors.push(color);
  }
  if (!colors.includes(fallback)) colors.unshift(fallback);
  return colors.length ? colors : [fallback];
}

function stimulusInventorySources() {
  return [
    ...(state?.design?.noises || []).map((source) => ({
      ...source,
      source_kind: "generated_noise",
      color_key: source.noise_type || "pink"
    })),
    ...(state?.design?.custom_looming_files || []).map((source) => ({
      ...source,
      source_kind: "imported_audio",
      color_key: source.tone_type || source.noise_type || "custom_audio"
    }))
  ];
}

function trajectoryGroupKey(snapshot = {}) {
  if (!snapshot || snapshot.start_distance_cm === undefined || snapshot.end_distance_cm === undefined) return "";
  const fields = [
    "start_distance_cm",
    "end_distance_cm",
    "start_rotation_deg",
    "end_rotation_deg",
    "movement_duration_s",
    "start_hold_s",
    "end_hold_s"
  ];
  const controlKey = fields.map((field) => roundedKeyPart(snapshot[field])).join("|");
  const start = snapshot.start || {};
  const end = snapshot.end || {};
  const coordinateKey = ["x_m", "y_m", "z_m"]
    .map((field) => `${roundedKeyPart(start[field])}:${roundedKeyPart(end[field])}`)
    .join("|");
  return `${controlKey}|${coordinateKey}`;
}

function roundedKeyPart(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4) : "";
}

function sourceColor(key = "custom_audio") {
  return STIMULUS_TRAJECTORY_COLORS[String(key || "").toLowerCase()] || STIMULUS_TRAJECTORY_COLORS.custom_audio;
}

function sourceColorOptions(selected = "custom_audio") {
  const selectedValue = String(selected || "custom_audio").toLowerCase();
  return SOURCE_COLOR_OPTIONS.map((item) =>
    `<option value="${escapeAttr(item.value)}" ${item.value === selectedValue ? "selected" : ""}>${escapeHtml(item.label)}</option>`
  ).join("");
}

function applySourceCardColor(card, colorKey = "custom_audio") {
  if (!card) return;
  const color = sourceColor(colorKey);
  card.style.setProperty("--source-card-color", color);
  card.style.setProperty("--source-card-color-soft", colorWithAlpha(color, 0.12));
}

function colorWithAlpha(hex, alpha = 0.12) {
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(String(hex || ""));
  if (!match) return `rgba(36, 107, 85, ${alpha})`;
  const [, r, g, b] = match;
  return `rgba(${Number.parseInt(r, 16)}, ${Number.parseInt(g, 16)}, ${Number.parseInt(b, 16)}, ${Math.max(0, Math.min(1, alpha))})`;
}

function trajectoryGradient(colors = []) {
  const safeColors = (colors.length ? colors : [sourceColor("custom_audio")]).map((color) => color || sourceColor("custom_audio"));
  if (safeColors.length === 1) return safeColors[0];
  const stops = [];
  const width = 100 / safeColors.length;
  safeColors.forEach((color, index) => {
    const start = Math.round(index * width * 10) / 10;
    const end = Math.round((index + 1) * width * 10) / 10;
    stops.push(`${color} ${start}%`, `${color} ${end}%`);
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

function trajectorySnapshotForSource(source = {}, colorKey = "custom_audio", sourceKind = "") {
  const snapshot = source.trajectory_snapshot && typeof source.trajectory_snapshot === "object"
    ? clone(source.trajectory_snapshot)
    : {};
  if (snapshot.start_distance_cm !== undefined && snapshot.end_distance_cm !== undefined) {
    return snapshot;
  }
  if (sourceKind === "fixed_audio") return {};
  if (String(source.motion_mode || "").toLowerCase() === "stationary") return {};
  const controls = state.trajectory_controls || currentTrajectoryControls();
  return {
    schema: "pps-stimulus-trajectory.v1",
    label: source.label || "",
    source_kind: sourceKind,
    noise_type: colorKey,
    start_distance_cm: controls.start_distance_cm,
    end_distance_cm: controls.end_distance_cm,
    start_rotation_deg: controls.start_rotation_deg,
    end_rotation_deg: controls.end_rotation_deg,
    movement_duration_s: controls.movement_duration_s,
    start_hold_s: controls.start_hold_s,
    end_hold_s: controls.end_hold_s,
    path_length_m: Math.max(0, Math.abs(Number(controls.start_distance_cm || 0) - Number(controls.end_distance_cm || 0)) / 100),
  };
}

function readJsonField(field) {
  if (!field) return {};
  try {
    const value = JSON.parse(field.value || "{}");
    return value && typeof value === "object" ? value : {};
  } catch (_error) {
    return {};
  }
}

function sourceFolderAction(path) {
  if (!path) return "";
  return `<button type="button" class="source-folder-link" data-open-folder="${escapeAttr(path)}">Open Folder</button>`;
}

function renderedWavForLabel(label) {
  const target = normalizeSourceKey(label);
  if (!target) return null;
  return (state.render?.wavs || []).find((wav) => {
    const keys = [
      wav.label,
      wav.path,
      String(wav.path || "").split(/[\\/]/).pop(),
      String(wav.path || "").split(/[\\/]/).pop()?.replace(/^looming_/i, "").replace(/\.[^.]+$/, ""),
    ];
    return keys.some((key) => normalizeSourceKey(key) === target);
  }) || null;
}

function normalizeSourceKey(value) {
  return String(value || "")
    .replace(/^looming[_\s-]*/i, "")
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase();
}

function renderSourceCounts() {
  const generated = $("noise-list").querySelectorAll(".noise-source-card").length;
  const audioCards = [...$("audio-list").querySelectorAll(".audio-source-card")];
  const snippetCards = [...$("snippet-list").querySelectorAll(".audio-source-card")];
  const imported = audioCards.filter((card) => card.dataset.audioRole !== "prestimulus").length;
  const prestimulus = audioCards.filter((card) => card.dataset.audioRole === "prestimulus").length
    + snippetCards.filter((card) => card.dataset.audioRole === "prestimulus").length;
  const stimulusSources = generated + imported + prestimulus;
  const sourceLabel = `${stimulusSources} local source${stimulusSources === 1 ? "" : "s"}`;
  $("source-counts").textContent = sourceLabel;
  $("source-counts").className = `status-label ${stimulusSources ? "ready" : "required"}`;
  if ($("snippet-counts")) {
    $("snippet-counts").textContent = `${prestimulus} clip${prestimulus === 1 ? "" : "s"}`;
    $("snippet-counts").className = `status-label ${prestimulus ? "ready" : "required"}`;
  }
}

function renderSegmentRegistryOutputs() {
  updateSegmentFolderButton("0_profile", "open-profile-folder");
  updateSegmentFolderButton("1_core_audio_ingredients", "open-ingredient-folder");
  updateSegmentFolderButton("2_trial_sequence_designs", "open-trial-sequence-folder");

  const segment1 = projectSegment("1_core_audio_ingredients");
  const segment2 = projectSegment("2_trial_sequence_designs");
  const sequence = sequenceVariantEstimate();
  const sequenceButton = $("bake-trial-sequences");
  const sequenceStatus = $("trial-sequence-bake-status");
  const segment1Ready = segment1.status === "ready";
  const sequenceReadyToBake = segment1Ready && sequence.variantCount > 0;
  if (sequenceButton) sequenceButton.disabled = !sequenceReadyToBake;
  if (sequenceStatus) {
    sequenceStatus.textContent = segment2.status === "ready"
      ? `${segment2.variant_count || 0} variants`
      : (sequenceReadyToBake ? "ready to bake" : "waiting");
    sequenceStatus.className = `status-label ${segment2.status === "ready" || sequenceReadyToBake ? "ready" : "required"}`;
  }

  const segment3 = projectSegment("3_tactile_and_baseline_trials");
  const trialButton = $("bake-trial-files");
  const segment2Ready = segment2.status === "ready";
  const hasSoas = parseIntegerList($("block-soa-values")?.value || $("soa-values")?.value || "").length > 0;
  if (trialButton) trialButton.disabled = !(segment2Ready && hasSoas);
  updateSegmentFolderButton("3_tactile_and_baseline_trials", "open-trial-file-folder");
  const trialStatus = $("trial-file-bake-status");
  if (trialStatus) {
    trialStatus.textContent = segment3.status === "ready"
      ? `${segment3.total_count || 0} files`
      : (segment2Ready ? "ready to bake" : "waiting for Segment 2");
    trialStatus.className = `status-label ${segment3.status === "ready" || segment2Ready ? "ready" : "required"}`;
  }

  const segment4 = projectSegment("4_trial_repetition_pool");
  const poolButton = $("bake-trial-pool");
  const segment3Ready = segment3.status === "ready";
  if (poolButton) poolButton.disabled = !segment3Ready || trialPoolCompositionEstimate().totalTrials <= 0;
  const poolStatus = $("trial-pool-bake-status");
  if (poolStatus) {
    poolStatus.textContent = segment4.status === "ready"
      ? `${segment4.total_count || 0} rows`
      : (segment3Ready ? "ready to bake" : "waiting for Segment 3");
    poolStatus.className = `status-label ${segment4.status === "ready" || segment3Ready ? "ready" : "required"}`;
  }
  const poolOpenButton = $("open-trial-pool-folder");
  if (poolOpenButton) {
    poolOpenButton.disabled = !segment4.folder_path;
    poolOpenButton.dataset.folderPath = segment4.folder_path || "";
  }

  const segment5 = projectSegment("5_block_csv_preview");
  const blockButton = $("regenerate-block-csvs");
  const acceptButton = $("accept-block-csvs");
  const segment4Ready = segment4.status === "ready";
  const blockAccepted = Boolean(segment5.accepted || state.block_csv_preview?.accepted);
  if (blockButton) blockButton.disabled = !segment4Ready || blockAccepted;
  if (acceptButton) {
    acceptButton.disabled = !(segment5.status === "ready");
    acceptButton.textContent = blockAccepted ? "Edit Blocks" : "Accept Blocks";
  }
  const blockStatus = $("block-csv-bake-status");
  if (blockStatus) {
    blockStatus.textContent = segment5.status === "ready"
      ? `${segment5.block_count || 0} CSVs${blockAccepted ? " accepted" : ""}`
      : (segment4Ready ? "ready to bake" : "waiting for Segment 4");
    blockStatus.className = `status-label ${segment5.status === "ready" || segment4Ready ? "ready" : "required"}`;
  }
}

function projectSegment(folderName) {
  return state?.project_segments?.[folderName] || {};
}

function updateSegmentFolderButton(folderName, buttonId) {
  const segment = projectSegment(folderName);
  const button = $(buttonId);
  if (button) {
    button.disabled = !segment.folder_path;
    button.dataset.folderPath = segment.folder_path || "";
  }
}

function latestBlockCsvJob() {
  const jobs = state?.jobs || [];
  return jobs.find((job) => job.kind === "block_csv_preview" || job.result?.source_kind === "block_csv_preview") || null;
}

function setBlockProgress(current, total, label) {
  const safeTotal = Math.max(0, Number(total || 0));
  const safeCurrent = Math.max(0, Math.min(Number(current || 0), safeTotal || Number(current || 0)));
  const percent = safeTotal ? Math.round((safeCurrent / safeTotal) * 1000) / 10 : 0;
  const track = $("block-build-progress-track");
  if (track) {
    track.style.setProperty("--block-progress", String(percent));
    track.setAttribute("aria-valuenow", String(percent));
  }
  if ($("block-build-progress-label")) $("block-build-progress-label").textContent = label || "waiting";
  if ($("block-build-progress-count")) $("block-build-progress-count").textContent = `${safeCurrent} / ${safeTotal} blocks`;
  if ($("block-build-progress-percent")) $("block-build-progress-percent").textContent = `${percent}%`;
}

function renderBlockCsvPreview() {
  const blockInput = $("block-count");
  const protocolBlocks = Math.max(1, Math.round(Number(state?.design?.protocol?.blocks || $("blocks")?.value || 1)));
  if (blockInput && document.activeElement !== blockInput) blockInput.value = protocolBlocks;
  const segment5 = projectSegment("5_block_csv_preview");
  const preview = state.block_csv_preview || {};
  const blockAccepted = Boolean(segment5.accepted || preview.accepted);
  if (blockInput) blockInput.disabled = blockAccepted;
  if ($("blocks")) $("blocks").value = blockInput?.value || protocolBlocks;
  const job = latestBlockCsvJob();
  if (job?.status === "running" || job?.status === "queued") {
    setBlockProgress(job.progress_current || 0, job.progress_total || protocolBlocks, job.progress_label || "creating block CSVs");
  } else if (segment5.status === "ready") {
    setBlockProgress(
      preview.block_count || segment5.block_count || 0,
      preview.block_count || segment5.block_count || 0,
      (preview.accepted || segment5.accepted) ? "accepted" : "ready"
    );
  } else {
    setBlockProgress(0, protocolBlocks, segment5.last_validation_message || "waiting");
  }

  const list = $("block-csv-preview-list");
  if (!list) return;
  const blocks = preview.blocks || [];
  if (!blocks.length) {
    list.innerHTML = `<div class="summary-text">No block CSVs yet.</div>`;
    return;
  }
  list.innerHTML = blocks.map((block, index) => renderBlockPreviewCard(block, index)).join("");
}

function renderBlockPreviewCard(block, index = 0) {
  const rows = block.preview_rows || [];
  const familyCounts = block.family_counts || {};
  const total = Number(block.trial_count || rows.length || 0);
  const distribution = ["audio_tactile", "baseline", "catch"].map((family) => {
    const count = Number(familyCounts[family] || 0);
    return `
      <div class="block-distribution-segment" style="--segment-color:${escapeAttr(TRIAL_FAMILY_COLORS[family] || "#68746c")}">
        ${escapeHtml(familyDisplayName(family))}: ${count}
      </div>
    `;
  }).join("");
  const meta = [
    ...blockFeatureChips(block.row_label_counts, "Row", rows, "row_label", "family_color_hex", 4),
    ...blockFeatureChips(block.soa_counts, "SOA", rows, "soa_ms", "soa_color_hex", 6),
    ...blockFeatureChips(block.noise_type_counts, "Noise", rows, "noise_type", "noise_color_hex", 5),
  ].join("");
  const bodyRows = rows.map(renderBlockPreviewRow).join("");
  const csvName = block.csv_file_name || "";
  return `
    <details class="block-preview-card" ${index === 0 ? "open" : ""}>
      <summary>
        <div>
          <strong>${escapeHtml(block.block_label || `Block ${block.block_index || ""}`)}</strong>
          <span>${escapeHtml(csvName)}</span>
        </div>
        <div class="block-distribution">${distribution}</div>
        <span>${total} trials / ${escapeHtml(formatDurationMs(block.duration_ms || 0))}</span>
      </summary>
      <div class="block-preview-body">
        <div class="block-preview-meta">${meta}</div>
        <div class="scroll-table compact">
          <table class="data-table compact block-preview-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Family</th>
                <th>Row</th>
                <th>SOA</th>
                <th>Noise</th>
                <th>Sequence</th>
                <th>Duration</th>
                <th>WAV</th>
              </tr>
            </thead>
            <tbody>${bodyRows}</tbody>
          </table>
        </div>
      </div>
    </details>
  `;
}

function blockFeatureChips(counts = {}, prefix, rows, valueKey, colorKey, limit) {
  const colorByValue = new Map();
  for (const row of rows || []) {
    const value = String(row[valueKey] || "");
    if (value && !colorByValue.has(value)) colorByValue.set(value, row[colorKey] || "#68746c");
  }
  return Object.entries(counts)
    .filter(([value]) => value)
    .slice(0, limit)
    .map(([value, count]) => `
      <span class="feature-chip" style="--chip-color:${escapeAttr(colorByValue.get(value) || "#68746c")}">
        ${escapeHtml(prefix)} ${escapeHtml(value)}: ${escapeHtml(count)}
      </span>
    `);
}

function renderBlockPreviewRow(row) {
  return `
    <tr>
      <td>${escapeHtml(row.block_trial_index || "")}</td>
      ${coloredPreviewCell(row.family_label || familyDisplayName(row.family), row.family_color_hex)}
      ${coloredPreviewCell(row.row_label || "", row.row_color_hex)}
      ${coloredPreviewCell(row.soa_ms ? `${row.soa_ms} ms` : "", row.soa_color_hex)}
      ${coloredPreviewCell(row.noise_type || "", row.noise_color_hex)}
      <td>${escapeHtml(row.sequence_labels || row.sequence_variant_key || "")}</td>
      <td>${escapeHtml(formatDurationMs(row.duration_ms || 0))}</td>
      <td>${escapeHtml(row.source_file_name || "")}</td>
    </tr>
  `;
}

function coloredPreviewCell(value, color) {
  return `<td class="preview-color-cell" style="--cell-color:${escapeAttr(color || "transparent")}">${escapeHtml(value || "")}</td>`;
}

function stimulusTargetOptionsFromDesign(selected = "") {
  const options = stimulusSourceOptionsFromDesign();
  return renderOptionList(options, selected);
}

function stimulusSourceOptionsFromDesign() {
  const options = [{ value: "", label: "Every stimulus source" }];
  const seen = new Set([""]);
  for (const noise of state.design.noises || []) {
    addStimulusSourceOption(options, seen, noise.label || `${noiseTypeLabel(noise.noise_type)} noise`);
  }
  for (const audio of state.design.custom_looming_files || []) {
    addStimulusSourceOption(options, seen, audio.label || audioRoleTitle(audio.render_mode || "preserve"));
  }
  return options;
}

function stimulusSourceOptionsFromDom() {
  const options = [{ value: "", label: "Every stimulus source" }];
  const seen = new Set([""]);
  for (const card of $("noise-list").querySelectorAll(".noise-source-card")) {
    const label = card.querySelector('[data-field="label"]')?.value || "Generated noise";
    addStimulusSourceOption(options, seen, label);
  }
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const role = card.querySelector('[data-field="audio_role"]')?.value;
    if (role === "prestimulus") continue;
    const label = card.querySelector('[data-field="label"]')?.value || audioRoleTitle(role);
    addStimulusSourceOption(options, seen, label);
  }
  return options;
}

function addStimulusSourceOption(options, seen, label) {
  const value = String(label || "").trim();
  if (!value || seen.has(value)) return;
  seen.add(value);
  options.push({ value, label: value });
}

function stimulusPhaseOptions(selected = "") {
  const phases = state.design.protocol?.respiratory_phases || ["Inhale", "Exhale"];
  const options = [{ value: "", label: "Any phase" }];
  const seen = new Set([""]);
  for (const phase of phases) {
    const value = String(phase || "").trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({ value, label: value });
  }
  return renderOptionList(options, selected);
}

function renderOptionList(options, selected = "") {
  const selectedValue = String(selected || "");
  return options
    .map((item) => `<option value="${escapeAttr(item.value)}" ${item.value === selectedValue ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
}

function refreshAssemblyTargetOptions() {
  const options = stimulusSourceOptionsFromDom();
  for (const select of document.querySelectorAll('select[data-field="target_source_label"]')) {
    const selected = select.value || select.dataset.selectedTarget || "";
    select.innerHTML = renderOptionList(options, selected);
    select.value = options.some((item) => item.value === selected) ? selected : "";
    select.dataset.selectedTarget = select.value;
  }
}

function normalizeSnippetPlacement(value) {
  return value === "after" ? "after" : "before";
}

function renderTrials() {
  const protocol = state.design.protocol || {};
  syncTrialPoolDraftFromState();
  $("repetitions").value = formatRepetitionValue(trialPoolRepetitionDraft.defaultRepetitions ?? protocol.repetitions_per_condition ?? 1);
  const blockCount = Math.max(1, Math.round(Number(protocol.blocks || 1)));
  $("blocks").value = blockCount;
  if ($("block-count") && document.activeElement !== $("block-count")) $("block-count").value = blockCount;
  $("soa-values").value = formatList(protocol.soa_values_ms);
  $("block-soa-values").value = formatList(protocol.soa_values_ms);
  renderTrialStrips();
  renderProtocolSummary();
}

function formatDurationMs(ms) {
  const totalSeconds = Math.max(0, Math.round(Number(ms || 0) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`;
  if (minutes) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${seconds}s`;
}

function formatMillis(ms) {
  return `${Math.round(Number(ms || 0)).toLocaleString()} ms`;
}

function formatPercent(value) {
  const rounded = Math.round(Number(value || 0) * 10) / 10;
  return `${rounded}%`;
}

function slugify(value) {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "item";
}

function normalizeRepetitionValue(value, fallback = 0) {
  const parsed = Number(value);
  const base = Number.isFinite(parsed) ? parsed : Number(fallback || 0);
  return Math.max(0, Math.round(base * 2) / 2);
}

function formatRepetitionValue(value) {
  const normalized = normalizeRepetitionValue(value, 0);
  return Number.isInteger(normalized) ? String(normalized) : normalized.toFixed(1);
}

function trialPoolFamilyKey(value) {
  const key = String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (["audio", "target", "target_audio_tactile", "audio_tactile_trials"].includes(key)) return "audio_tactile";
  if (["baseline_trials", "tactile_baseline", "tactile_only"].includes(key)) return "baseline";
  if (["catch_trials", "audio_only"].includes(key)) return "catch";
  return key;
}

function stableHashInt(text) {
  let hash = 2166136261;
  const input = String(text || "");
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function trialPoolSubgroupLabel(file) {
  const label = String(file?.row_label || file?.row_folder_name || "").trim();
  if (/inhale/i.test(label)) return "Inhale";
  if (/exhale/i.test(label)) return "Exhale";
  return label || "Row";
}

function trialPoolSourceLineage(file) {
  const labels = String(file?.source_labels || file?.sequence_labels || "").trim();
  if (labels) {
    const pieces = labels.split("|").map((piece) => piece.trim()).filter(Boolean);
    if (pieces.length) return slugify(pieces[pieces.length - 1]);
  }
  return slugify(file?.sequence_variant_key || file?.variant_key || file?.source_file_name || file?.file_key || "source");
}

function trialPoolFractionalStratum(file, fractionalRemainder) {
  const family = trialPoolFamilyKey(file?.family);
  const rowKey = slugify(trialPoolSubgroupLabel(file));
  const soaMs = Math.round(Number(file?.soa_ms || 0));
  const mode = slugify(file?.baseline_mode || "none");
  return `${family}|${rowKey}|soa${soaMs}|${mode}|frac${formatRepetitionValue(fractionalRemainder)}`;
}

function trialPoolFractionalParentStratum(file, fractionalRemainder) {
  const family = trialPoolFamilyKey(file?.family);
  const rowKey = slugify(trialPoolSubgroupLabel(file));
  const mode = slugify(file?.baseline_mode || "none");
  return `${family}|${rowKey}|${mode}|frac${formatRepetitionValue(fractionalRemainder)}`;
}

function trialPoolFilesFromState() {
  return Array.isArray(state?.trial_file_bake?.files) ? state.trial_file_bake.files : [];
}

function syncTrialPoolDraftFromState() {
  const sourceHash = state?.trial_file_bake?.manifest_sha256 || "";
  if (trialPoolDraftInitialized && trialPoolDraftSourceHash === sourceHash) return;
  const settings = state?.trial_pool_bake?.settings || {};
  const protocol = state?.design?.protocol || {};
  const protocolDefaults = protocol.trial_pool_repetition_defaults || {};
  const defaultRepetitions = normalizeRepetitionValue(
    settings.default_repetitions ?? protocolDefaults.default ?? protocol.repetitions_per_condition ?? 1,
    1
  );
  const familyRepetitions = {};
  for (const [key, value] of Object.entries(protocolDefaults)) {
    const family = trialPoolFamilyKey(key);
    if (["audio_tactile", "baseline", "catch"].includes(family)) {
      familyRepetitions[family] = normalizeRepetitionValue(value, defaultRepetitions);
    }
  }
  for (const [key, value] of Object.entries(settings.family_repetitions || {})) {
    const family = trialPoolFamilyKey(key);
    if (["audio_tactile", "baseline", "catch"].includes(family)) {
      familyRepetitions[family] = normalizeRepetitionValue(value, defaultRepetitions);
    }
  }
  trialPoolRepetitionDraft = {
    defaultRepetitions,
    familyRepetitions,
    folderRepetitions: Object.fromEntries(Object.entries(settings.folder_repetitions || {}).map(([key, value]) => [key, normalizeRepetitionValue(value, defaultRepetitions)])),
    fileRepetitionOverrides: Object.fromEntries(Object.entries(settings.file_repetition_overrides || {}).map(([key, value]) => [key, normalizeRepetitionValue(value, defaultRepetitions)])),
    fractionalSeed: Number(settings.fractional_seed ?? protocol.random_seed ?? 20250604) || 20250604,
  };
  trialPoolDraftSourceHash = sourceHash;
  trialPoolDraftInitialized = true;
}

function trialPoolFolderGroups() {
  const groups = new Map();
  for (const file of trialPoolFilesFromState()) {
    const folderKey = file.folder_key || file.folder_name || "trial_files";
    if (!groups.has(folderKey)) {
      groups.set(folderKey, {
        folderKey,
        folderName: file.folder_name || folderKey,
        rowFolderName: file.row_folder_name || "",
        rowLabel: file.row_label || "",
        family: file.family || "",
        files: [],
      });
    }
    groups.get(folderKey).files.push(file);
  }
  return [...groups.values()].sort((a, b) => {
    const rowCompare = String(a.rowFolderName).localeCompare(String(b.rowFolderName));
    if (rowCompare) return rowCompare;
    return String(a.folderName).localeCompare(String(b.folderName));
  });
}

function repetitionForFolder(folderKey) {
  const group = trialPoolFolderGroups().find((item) => item.folderKey === folderKey);
  const family = trialPoolFamilyKey(group?.family);
  return normalizeRepetitionValue(
    trialPoolRepetitionDraft.folderRepetitions[folderKey]
      ?? trialPoolRepetitionDraft.familyRepetitions[family]
      ?? trialPoolRepetitionDraft.defaultRepetitions
      ?? 1,
    1
  );
}

function repetitionForFile(file) {
  const fileKey = file.file_key || "";
  if (fileKey && Object.prototype.hasOwnProperty.call(trialPoolRepetitionDraft.fileRepetitionOverrides, fileKey)) {
    return normalizeRepetitionValue(trialPoolRepetitionDraft.fileRepetitionOverrides[fileKey] || 0, 0);
  }
  return repetitionForFolder(file.folder_key || "");
}

function trialPoolCompositionEstimate() {
  const groups = trialPoolFolderGroups();
  const files = trialPoolFilesFromState();
  const records = files.map((file, index) => {
    const configured = repetitionForFile(file);
    const baseRepetitions = Math.floor(configured);
    const fractionalRemainder = normalizeRepetitionValue(configured - baseRepetitions, 0);
    return {
      file,
      index,
      configured,
      baseRepetitions,
      fractionalRemainder,
      fractionalExtra: false,
      balancingStratum: fractionalRemainder ? trialPoolFractionalStratum(file, fractionalRemainder) : "",
      balancingParentStratum: fractionalRemainder ? trialPoolFractionalParentStratum(file, fractionalRemainder) : "",
      sourceLineage: trialPoolSourceLineage(file),
    };
  });
  const warnings = [];
  const fractionalGroups = new Map();
  for (const record of records) {
    if (!record.fractionalRemainder) continue;
    if (!fractionalGroups.has(record.balancingStratum)) fractionalGroups.set(record.balancingStratum, []);
    fractionalGroups.get(record.balancingStratum).push(record);
  }
  const seed = Number(trialPoolRepetitionDraft.fractionalSeed || state?.design?.protocol?.random_seed || 20250604) || 20250604;
  const strataByParent = new Map();
  for (const [stratum, group] of fractionalGroups.entries()) {
    const parent = group[0]?.balancingParentStratum || stratum;
    if (!strataByParent.has(parent)) strataByParent.set(parent, []);
    strataByParent.get(parent).push(stratum);
  }
  const stratumOffsets = new Map();
  for (const [parent, strata] of strataByParent.entries()) {
    const orderedStrata = [...strata].sort((left, right) => {
      const leftSoa = Number(fractionalGroups.get(left)?.[0]?.file?.soa_ms || 0);
      const rightSoa = Number(fractionalGroups.get(right)?.[0]?.file?.soa_ms || 0);
      return leftSoa - rightSoa || left.localeCompare(right);
    });
    let runningOffset = stableHashInt(`${seed}|${parent}`);
    for (const stratum of orderedStrata) {
      const group = fractionalGroups.get(stratum) || [];
      const expectedExtra = group.length * (group[0]?.fractionalRemainder || 0);
      const extraCount = Math.max(0, Math.min(group.length, Math.floor(expectedExtra + 0.5)));
      stratumOffsets.set(stratum, group.length ? runningOffset % group.length : 0);
      runningOffset += extraCount;
    }
  }
  for (const [stratum, group] of [...fractionalGroups.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    const expectedExtra = group.length * group[0].fractionalRemainder;
    const extraCount = Math.max(0, Math.min(group.length, Math.floor(expectedExtra + 0.5)));
    if (Math.abs(expectedExtra - Math.round(expectedExtra)) > 0.000001) {
      warnings.push(`Fractional split cannot be exact for ${group.length} files in ${stratum}; ${extraCount} extra rows selected.`);
    }
    const ordered = [...group].sort((a, b) => {
      const left = `${a.sourceLineage}|${a.file.sequence_variant_key || a.file.variant_key || ""}|${a.file.source_file_name || ""}|${a.file.file_key || ""}`;
      const right = `${b.sourceLineage}|${b.file.sequence_variant_key || b.file.variant_key || ""}|${b.file.source_file_name || ""}|${b.file.file_key || ""}`;
      return left.localeCompare(right);
    });
    if (!ordered.length || !extraCount) continue;
    const offset = (stratumOffsets.get(stratum) || 0) % ordered.length;
    const rotated = ordered.slice(offset).concat(ordered.slice(0, offset));
    for (const record of rotated.slice(0, extraCount)) {
      record.fractionalExtra = true;
    }
  }
  const occurrenceByFileKey = new Map();
  for (const record of records) {
    const key = record.file.file_key || `source-${record.index}`;
    occurrenceByFileKey.set(key, record.baseRepetitions + (record.fractionalExtra ? 1 : 0));
  }
  const familyCounts = { audio_tactile: 0, baseline: 0, catch: 0 };
  const familyDurationMs = { audio_tactile: 0, baseline: 0, catch: 0 };
  const subgroupCounts = { audio_tactile: {}, baseline: {}, catch: {} };
  const subgroupDurationMs = { audio_tactile: {}, baseline: {}, catch: {} };
  const folderSummaries = [];
  let totalTrials = 0;
  let totalDurationMs = 0;
  for (const group of groups) {
    let folderTrials = 0;
    let folderDurationMs = 0;
    for (const file of group.files) {
      const reps = occurrenceByFileKey.get(file.file_key || "") ?? 0;
      const durationMs = Math.max(0, Number(file.duration_ms || 0));
      folderTrials += reps;
      folderDurationMs += reps * durationMs;
      if (Object.prototype.hasOwnProperty.call(familyCounts, file.family)) {
        familyCounts[file.family] += reps;
        familyDurationMs[file.family] += reps * durationMs;
        const subgroup = trialPoolSubgroupLabel(file);
        subgroupCounts[file.family][subgroup] = (subgroupCounts[file.family][subgroup] || 0) + reps;
        subgroupDurationMs[file.family][subgroup] = (subgroupDurationMs[file.family][subgroup] || 0) + reps * durationMs;
      }
    }
    totalTrials += folderTrials;
    totalDurationMs += folderDurationMs;
    folderSummaries.push({ ...group, trialCount: folderTrials, durationMs: folderDurationMs });
  }
  const percentages = {};
  for (const family of Object.keys(familyCounts)) {
    percentages[family] = totalTrials ? (100 * familyCounts[family] / totalTrials) : 0;
  }
  const longestFolder = folderSummaries.reduce((best, folder) => (
    !best || folder.durationMs > best.durationMs ? folder : best
  ), null);
  return {
    groups,
    folderSummaries,
    uniqueFiles: trialPoolFilesFromState().length,
    totalTrials,
    familyCounts,
    familyDurationMs,
    percentages,
    subgroupCounts,
    subgroupDurationMs,
    balanceWarnings: warnings,
    totalDurationMs,
    averageDurationMs: totalTrials ? totalDurationMs / totalTrials : 0,
    longestFolder,
  };
}

function renderProtocolSummary() {
  const summary = $("protocol-summary");
  summary.innerHTML = "";
  const composition = trialPoolCompositionEstimate();
  const rows = [
    ["Unique WAVs", composition.uniqueFiles, "total"],
    ["Total trials", composition.totalTrials, "total"],
    ["Audio-tactile", composition.familyCounts.audio_tactile, "audio"],
    ["Baseline", composition.familyCounts.baseline, "baseline"],
    ["Catch", composition.familyCounts.catch, "catch"],
  ];
  for (const [label, value, family] of rows) {
    const item = document.createElement("div");
    item.className = `summary-item count-chip ${family}`;
    item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    summary.appendChild(item);
  }
  renderTrialPoolFolderCards(composition);
  renderCompositionTree(composition);
}

function updatePercentMixerDisplay(composition = blockCompositionEstimate()) {
  const catchPercent = Math.max(0, Math.min(90, numberValue("catch-percent", 0)));
  const baselinePercent = !baselineStrategyIsActive()
    ? 0
    : Math.max(0, Math.min(90, numberValue("baseline-percent", 0)));
  const audioPercent = Math.max(0, 100 - catchPercent - baselinePercent);
  const setText = (id, text) => {
    const element = $(id);
    if (element) element.textContent = text;
  };
  setText("audio-percent-value", `${audioPercent}%`);
  setText("baseline-percent-value", `${baselinePercent}%`);
  setText("catch-percent-value", `${catchPercent}%`);
  const audioBar = $("audio-percent-bar");
  if (audioBar) audioBar.style.width = `${audioPercent}%`;
  if ($("baseline-percent")) $("baseline-percent").value = String(baselinePercent);
  if ($("catch-percent")) $("catch-percent").value = String(catchPercent);

  const warning = audioPercent <= 0 || composition.totalPerBlock <= 0;
  document.querySelector(".percent-mixer")?.classList.toggle("mix-warning", warning);
}

function compositionTreeRow(kind, label, expression, count) {
  return `
    <div class="tree-branch ${kind}">
      <span class="tree-dot"></span>
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(expression)}</span>
      </div>
      <b>${count}</b>
    </div>
  `;
}

function compositionSliderRow(kind, label, family, composition) {
  const percent = Math.max(0, Math.min(100, Number(composition.percentages[family] || 0)));
  const count = composition.familyCounts[family] || 0;
  const duration = formatDurationMs(composition.familyDurationMs[family] || 0);
  const percentLabel = formatPercent(percent);
  const subgroupOrder = (label) => (/inhale/i.test(label) ? 0 : (/exhale/i.test(label) ? 1 : 2));
  const subRows = Object.entries(composition.subgroupCounts?.[family] || {})
    .sort((a, b) => subgroupOrder(a[0]) - subgroupOrder(b[0]) || a[0].localeCompare(b[0]))
    .map(([subgroup, subgroupCount]) => {
      const totalPercent = composition.totalTrials ? (100 * subgroupCount / composition.totalTrials) : 0;
      const familyPercent = count ? (100 * subgroupCount / count) : 0;
      return `
        <div class="pool-subslider" style="--subslider-value: ${Math.max(0, Math.min(100, totalPercent)).toFixed(3)};">
          <div class="pool-subslider-label">
            <strong>${escapeHtml(subgroup)}</strong>
            <span>${escapeHtml(subgroupCount)} trials</span>
          </div>
          <div class="pool-subslider-track" role="meter" aria-label="${escapeAttr(`${label} ${subgroup}`)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${escapeAttr(totalPercent.toFixed(1))}">
            <span></span>
          </div>
          <div class="pool-subslider-meta">
            <span>${escapeHtml(formatPercent(totalPercent))} total</span>
            <span>${escapeHtml(formatPercent(familyPercent))} family</span>
          </div>
        </div>
      `;
    }).join("");
  return `
    <article class="pool-slider ${kind}" style="--slider-value: ${percent.toFixed(3)};">
      <div class="pool-slider-header">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(percentLabel)}</span>
      </div>
      <div class="pool-slider-track"
        role="meter"
        aria-label="${escapeAttr(label)} percentage"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow="${escapeAttr(percent.toFixed(1))}">
        <span class="pool-slider-fill"></span>
        <span class="pool-slider-thumb"></span>
      </div>
      <div class="pool-slider-meta">
        <span>${escapeHtml(count)} trial${count === 1 ? "" : "s"}</span>
        <span>${escapeHtml(duration)}</span>
      </div>
      ${subRows ? `<div class="pool-subsliders">${subRows}</div>` : ""}
    </article>
  `;
}

function durationCalculusFamilyRow(kind, label, family, composition) {
  const count = composition.familyCounts[family] || 0;
  const totalMs = composition.familyDurationMs[family] || 0;
  const exactFormula = count
    ? `sum(duration_ms x reps) = ${formatMillis(totalMs)}`
    : `sum(duration_ms x reps) = 0 ms`;
  return `
    <div class="duration-calculus-row ${kind}">
      <span>${escapeHtml(label)}</span>
      <code>${escapeHtml(exactFormula)}</code>
      <strong>${escapeHtml(formatDurationMs(totalMs))}</strong>
    </div>
  `;
}

function renderTrialPoolDurationCalculus(composition) {
  const container = $("trial-pool-duration-calculus");
  if (!container) return;
  const total = formatDurationMs(composition.totalDurationMs);
  const average = composition.totalTrials ? formatDurationMs(composition.averageDurationMs) : "0s";
  container.innerHTML = `
    <div class="duration-calculus-heading">
      <strong>Duration Calculus</strong>
      <span>${escapeHtml(total)}</span>
    </div>
    ${durationCalculusFamilyRow("audio", "Audio-tactile", "audio_tactile", composition)}
    ${durationCalculusFamilyRow("baseline", "Baseline", "baseline", composition)}
    ${durationCalculusFamilyRow("catch", "Catch", "catch", composition)}
    <div class="duration-calculus-total">
      <span>Total</span>
      <code>${escapeHtml(formatDurationMs(composition.familyDurationMs.audio_tactile || 0))} + ${escapeHtml(formatDurationMs(composition.familyDurationMs.baseline || 0))} + ${escapeHtml(formatDurationMs(composition.familyDurationMs.catch || 0))}</code>
      <strong>${escapeHtml(total)}</strong>
    </div>
    <div class="duration-calculus-total muted-total">
      <span>Average trial</span>
      <code>${escapeHtml(formatMillis(composition.totalDurationMs))} / ${composition.totalTrials || 0} trials</code>
      <strong>${escapeHtml(average)}</strong>
    </div>
  `;
}

function familyDisplayName(family) {
  return {
    audio_tactile: "Audio-tactile",
    baseline: "Baseline",
    catch: "Catch",
  }[family] || humanize(family || "trial");
}

function renderTrialPoolFolderCards(composition = trialPoolCompositionEstimate()) {
  const container = $("trial-pool-folder-list");
  if (!container) return;
  if (!composition.groups.length) {
    container.innerHTML = `<div class="summary-text">Bake Segment 3 trial files before assigning repetitions.</div>`;
    return;
  }
  container.innerHTML = composition.groups.map((group) => {
    const folderReps = repetitionForFolder(group.folderKey);
    const fileRows = group.files.map((file) => {
      const fileReps = repetitionForFile(file);
      const inherited = !Object.prototype.hasOwnProperty.call(trialPoolRepetitionDraft.fileRepetitionOverrides, file.file_key || "");
      return `
        <tr>
          <td>${escapeHtml(file.source_file_name || "")}</td>
          <td>${formatDurationMs(file.duration_ms || 0)}</td>
          <td>${escapeHtml(file.soa_ms ?? "")}</td>
          <td>
            <input data-trial-pool-file="${escapeAttr(file.file_key || "")}" type="number" min="0" max="1000" step="0.5" value="${escapeAttr(formatRepetitionValue(fileReps))}" aria-label="File repetitions">
            <span class="muted">${inherited ? "folder" : "custom"}</span>
          </td>
        </tr>
      `;
    }).join("");
    const rowLabel = group.rowLabel || group.rowFolderName || "Row";
    const folderSummary = composition.folderSummaries.find((item) => item.folderKey === group.folderKey) || {};
    return `
      <article class="trial-pool-folder-card ${escapeAttr(group.family || "")}">
        <div class="trial-pool-folder-header">
          <div>
            <strong>${escapeHtml(familyDisplayName(group.family))}</strong>
            <span>${escapeHtml(rowLabel)} / ${escapeHtml(group.folderName)}</span>
          </div>
          <label>
            <span>Reps</span>
            <input data-trial-pool-folder="${escapeAttr(group.folderKey)}" type="number" min="0" max="1000" step="0.5" value="${escapeAttr(formatRepetitionValue(folderReps))}">
          </label>
        </div>
        <div class="trial-pool-folder-metrics">
          <span>${group.files.length} WAVs</span>
          <span>${folderSummary.trialCount || 0} trials</span>
          <span>${formatDurationMs(folderSummary.durationMs || 0)}</span>
        </div>
        <details class="trial-pool-file-details">
          <summary>Files</summary>
          <table class="data-table compact">
            <thead><tr><th>WAV</th><th>Duration</th><th>SOA</th><th>Reps</th></tr></thead>
            <tbody>${fileRows}</tbody>
          </table>
        </details>
      </article>
    `;
  }).join("");
}

function currentSoaValues() {
  return parseIntegerList($("block-soa-values")?.value || $("soa-values")?.value || "");
}

function renderCompositionTree(composition, context = {}) {
  const tree = $("composition-tree");
  if (!tree) return;
  const balanceMessage = composition.balanceWarnings?.length
    ? composition.balanceWarnings[0]
    : "Half-step repetitions use deterministic row/SOA/source-lineage balancing.";
  const balanceClass = composition.balanceWarnings?.length ? "warning" : "ready";
  tree.innerHTML = `
    ${compositionSliderRow("audio", "Audio-tactile", "audio_tactile", composition)}
    ${compositionSliderRow("baseline", "Baseline", "baseline", composition)}
    ${compositionSliderRow("catch", "Catch", "catch", composition)}
    <div class="balance-note ${balanceClass}">${escapeHtml(balanceMessage)}</div>
  `;
  renderTrialPoolDurationCalculus(composition);
}

function sequenceVariantEstimate() {
  const rows = [...$("filmstrip-list").querySelectorAll(".filmstrip-row")];
  if (!rows.length) return { rowCount: 0, variantCount: 0, rowVariants: [] };
  const rowVariants = rows.map((row, index) => {
    const label = row.querySelector('[data-strip-field="label"]')?.value.trim() || `Trial type ${index + 1}`;
    return { label, count: rowSourceCount(row) };
  });
  return {
    rowCount: rows.length,
    variantCount: rowVariants.reduce((total, row) => total + row.count, 0),
    rowVariants,
  };
}

function baselineAnchorSpecsFromInputs() {
  const strategy = currentBaselineStrategy();
  const soaValues = currentSoaValues();
  if (!baselineStrategyIsActive(strategy)) return [];
  if (strategy === "min_anchor") {
    return soaValues.length ? [{ label: "minimum", soa_ms: soaValues[0], mode: "audio_tactile" }] : [];
  }
  if (strategy === "max_anchor") {
    return soaValues.length ? [{ label: "maximum", soa_ms: soaValues[soaValues.length - 1], mode: "audio_tactile" }] : [];
  }
  if (strategy === "min_max") {
    return Array.from(new Set([soaValues[0], soaValues[soaValues.length - 1]].filter((value) => Number.isFinite(value))))
      .map((soa, index) => ({ label: index === 0 ? "minimum" : "maximum", soa_ms: soa, mode: "audio_tactile" }));
  }
  if (strategy === "tactile_only") {
    return soaValues.map((soa) => ({ label: "full SOA tactile-only", soa_ms: soa, mode: "tactile_only" }));
  }
  if (strategy === "custom") {
    const mode = $("baseline-custom-audio-tactile")?.checked ? "audio_tactile" : "tactile_only";
    return parseIntegerList($("baseline-soa-values").value).map((soa) => ({ label: "custom", soa_ms: soa, mode }));
  }
  return derivedBaselineTimingsMs(strategy).map((soa) => ({ label: strategy, soa_ms: soa, mode: "audio_tactile" }));
}

function renderBaselineTactileSummary() {
  const strip = $("baseline-count-strip");
  const tree = $("baseline-factor-tree");
  if (!strip || !tree) return;

  const sequence = sequenceVariantEstimate();
  const soaValues = currentSoaValues();
  const anchors = baselineAnchorSpecsFromInputs();
  const includeCatch = $("include-catch-trials")?.checked || false;
  const audioFiles = sequence.variantCount * soaValues.length;
  const baselineFiles = sequence.variantCount * anchors.length;
  const catchFiles = includeCatch ? sequence.variantCount : 0;
  const folderCount = sequence.rowCount * (audioFiles ? 1 : 0) + sequence.rowCount * (baselineFiles ? 1 : 0) + sequence.rowCount * (catchFiles ? 1 : 0);

  const rows = [
    ["Row variants", sequence.variantCount, "total"],
    ["SOAs", soaValues.length, "audio"],
    ["Audio-tactile files", audioFiles, "audio"],
    ["Baseline anchors", anchors.length, "baseline"],
    ["Baseline files", baselineFiles, "baseline"],
    ["Catch files", catchFiles, "catch"],
    ["Output folders", folderCount, "total"],
  ];
  strip.innerHTML = rows.map(([label, value, family]) => `
    <div class="summary-item count-chip ${family}">
      <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");

  const strategy = currentBaselineStrategy();
  const strategyNote = BASELINE_STRATEGY_NOTES[strategy] || BASELINE_STRATEGY_NOTES[""];
  const rowLabel = sequence.rowVariants.length
    ? sequence.rowVariants.map((row) => `${row.label}: ${row.count}`).join("; ")
    : "No trial-sequence rows yet";
  const audioExpression = `${sequence.variantCount} row variant${sequence.variantCount === 1 ? "" : "s"} x ${soaValues.length} SOA${soaValues.length === 1 ? "" : "s"}`;
  const baselineExpression = baselineStrategyIsActive(strategy)
    ? `${anchors.length} anchor${anchors.length === 1 ? "" : "s"}; ${strategyNote.note}`
    : (strategy === "none" ? "No baseline files will be created" : "Choose baseline handling");
  const catchExpression = includeCatch
    ? `${sequence.variantCount} row variant${sequence.variantCount === 1 ? "" : "s"} copied from Segment 2 audio`
    : "Catch file generation disabled";
  tree.innerHTML = `
    <div class="tree-root">
      <strong>Segment 3 trial files</strong>
      <span>${escapeHtml(rowLabel)}</span>
    </div>
    ${compositionTreeRow("audio", "Audio-tactile files", audioExpression, audioFiles)}
    ${compositionTreeRow("baseline", "Baseline files", baselineExpression, baselineFiles)}
    ${compositionTreeRow("catch", "Catch files", catchExpression, catchFiles)}
  `;

  const bake = state.trial_file_bake || {};
  const ready = Boolean(bake.manifest_exists);
  const status = $("trial-file-bake-status");
  if (status) {
    const total = Number(bake.total_count || 0);
    status.textContent = ready ? `${total} files` : "waiting";
    status.className = `status-label ${ready ? "ready" : ""}`;
  }
  const openButton = $("open-trial-file-folder");
  if (openButton) {
    openButton.disabled = !bake.root;
    openButton.dataset.folderPath = bake.root || "";
  }
}

function renderRowMixOverrides(composition = blockCompositionEstimate()) {
  const container = $("row-mix-overrides");
  if (!container) return;
  if (container.contains(document.activeElement) && document.activeElement?.matches?.("[data-row-mix-index][data-row-mix-field]")) {
    return;
  }
  const rows = [...$("filmstrip-list").querySelectorAll(".filmstrip-row")];
  if (!rows.length) {
    container.innerHTML = `<div class="summary-text">Add a trial-sequence row to override its block composition.</div>`;
    return;
  }
  const body = rows.map((row, index) => {
    const label = row.querySelector('[data-strip-field="label"]')?.value.trim() || `Trial type ${index + 1}`;
    const counts = composition.rows[index] || rowCompositionCounts(row);
    const mix = counts.mix;
    return `
      <tr>
        <td>${escapeHtml(label)}</td>
        <td><input data-row-mix-index="${index}" data-row-mix-field="audio_tactile_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.audioTactile)}"></td>
        <td><input data-row-mix-index="${index}" data-row-mix-field="baseline_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.baseline)}"></td>
        <td><input data-row-mix-index="${index}" data-row-mix-field="catch_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.catch)}"></td>
        <td>${counts.totalPerBlock}</td>
      </tr>
    `;
  }).join("");
  container.innerHTML = `
    <table class="data-table compact">
      <thead>
        <tr>
          <th>Row</th>
          <th>Audio %</th>
          <th>Baseline %</th>
          <th>Catch %</th>
          <th>Trials / block</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function renderBaseline() {
  const protocol = state.design.protocol || {};
  const savedStrategy = protocol.baseline_strategy === ""
    ? ""
    : (protocol.include_baseline_trials === false ? "none" : (protocol.baseline_strategy || "tactile_only"));
  $("catch-percent").value = protocol.catch_trial_percentage ?? 0;
  if ($("include-catch-trials")) $("include-catch-trials").checked = Boolean(protocol.include_catch_trials);
  $("baseline-percent").value = !savedStrategy || savedStrategy === "none" ? 0 : (protocol.baseline_trial_percentage ?? 0);
  $("baseline-soa-values").value = formatList(protocol.baseline_soa_values_ms || []);
  $("baseline-custom-audio-tactile").checked = protocol.baseline_custom_trial_mode === "audio_tactile";
  setBaselineStrategy(savedStrategy);
  updateBaselineDecision();
  renderBaselineTactileSummary();
}

function currentBaselineStrategy() {
  return $("baseline-strategy").value || "";
}

function baselineStrategyIsActive(strategy = currentBaselineStrategy()) {
  return Boolean(strategy && strategy !== "none");
}

function baselineOptionInputs() {
  return [...document.querySelectorAll('input[name="baseline-option"]')];
}

function setBaselineStrategy(strategy) {
  const nextStrategy = strategy || "";
  $("baseline-strategy").value = nextStrategy;
  if ($("baseline-strategy").value !== nextStrategy) $("baseline-strategy").value = "none";
  $("baseline-enabled").checked = Boolean($("baseline-strategy").value && $("baseline-strategy").value !== "none");
  syncBaselineStrategyControls();
}

function syncBaselineStrategyControls() {
  const strategy = $("baseline-strategy").value || "";
  $("baseline-strategy").value = strategy;
  $("baseline-enabled").checked = Boolean(strategy && strategy !== "none");
  for (const input of baselineOptionInputs()) {
    input.disabled = false;
    input.checked = baselineOptionCheckedForStrategy(input.value, strategy);
    input.closest(".baseline-option-card")?.classList.toggle("active", input.checked);
    input.closest(".baseline-option-card")?.classList.remove("disabled");
  }
  if ($("baseline-custom-controls")) $("baseline-custom-controls").hidden = strategy !== "custom";
}

function baselineOptionCheckedForStrategy(value, strategy) {
  if (!strategy) return false;
  if (strategy === "min_max") return value === "min_anchor" || value === "max_anchor";
  return value === strategy;
}

function strategyFromBaselineCheckboxes(changedInput = null) {
  const checked = new Set(baselineOptionInputs().filter((input) => input.checked).map((input) => input.value));
  const changed = changedInput?.value || "";
  if (changed === "none" && changedInput.checked) return "none";
  if (changed === "custom" && changedInput.checked) return "custom";
  if (changed === "tactile_only" && changedInput.checked) return "tactile_only";
  checked.delete("none");
  checked.delete("custom");
  checked.delete("tactile_only");
  const wantsMin = checked.has("min_anchor");
  const wantsMax = checked.has("max_anchor");
  if (wantsMin && wantsMax) return "min_max";
  if (wantsMin) return "min_anchor";
  if (wantsMax) return "max_anchor";
  return "";
}

function derivedBaselineTimingsMs(strategy = currentBaselineStrategy()) {
  if (strategy === "none" || !strategy) return [];
  const soaValues = currentSoaValues();
  if (strategy === "min_anchor") {
    return soaValues.length ? [soaValues[0]] : [];
  }
  if (strategy === "max_anchor") {
    return soaValues.length ? [soaValues[soaValues.length - 1]] : [];
  }
  if (strategy === "min_max") {
    if (!soaValues.length) return [];
    return Array.from(new Set([soaValues[0], soaValues[soaValues.length - 1]]));
  }
  if (strategy === "soa_zero") return [0];
  if (strategy === "sound_offset") {
    const controls = currentTrajectoryControls();
    return [Math.round((controls.start_hold_s + controls.movement_duration_s + controls.end_hold_s) * 1000)];
  }
  const custom = parseIntegerList($("baseline-soa-values").value);
  if (custom.length) return custom;
  if (strategy === "custom") return [];
  return soaValues;
}

function enforceGlobalPercentBounds(changedId = "") {
  const maxExtra = 99;
  let catchPercent = Math.max(0, Math.min(90, numberValue("catch-percent", 0)));
  let baselinePercent = !baselineStrategyIsActive()
    ? 0
    : Math.max(0, Math.min(90, numberValue("baseline-percent", 0)));
  if (catchPercent + baselinePercent > maxExtra) {
    if (changedId === "baseline-percent") {
      catchPercent = Math.max(0, maxExtra - baselinePercent);
    } else {
      baselinePercent = Math.max(0, maxExtra - catchPercent);
    }
  }
  $("catch-percent").value = String(catchPercent);
  $("baseline-percent").value = String(baselinePercent);
}

function eventSequenceAudioCountPerBlock() {
  return blockCompositionEstimate().audioPerBlock;
}

function tactileSiteCount() {
  return Math.max(1, (state.design.protocol?.tactile_sites || ["hand"]).length);
}

function rowSourceCount(row) {
  let count = 1;
  for (const card of row.querySelectorAll(".filmstrip-element")) {
    if (card.dataset.elementKind === "jitter") {
      count *= Math.max(0, parseIntegerList(card.querySelector('[data-element-field="jitter_values_ms"]')?.value).length);
    } else {
      const hidden = card.querySelectorAll('input[data-element-field="source_labels"][type="hidden"]');
      const checked = card.querySelectorAll('input[data-element-field="source_labels"]:checked');
      const selectedOptions = card.querySelectorAll('select[data-element-field="source_labels"] option:checked');
      count *= Math.max(0, hidden.length || checked.length || selectedOptions.length);
    }
  }
  return count;
}

function rowAudioCountPerBlock(row) {
  const soaCount = currentSoaValues().length;
  const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
  return rowSourceCount(row) * Math.max(soaCount, 0) * repetitions * tactileSiteCount();
}

function defaultRowMix() {
  const catchPercent = Math.max(0, Math.min(99, numberValue("catch-percent", 0)));
  const baselinePercent = !baselineStrategyIsActive()
    ? 0
    : Math.max(0, Math.min(99, numberValue("baseline-percent", 0)));
  return {
    audioTactile: Math.max(1, 100 - catchPercent - baselinePercent),
    catch: catchPercent,
    baseline: baselinePercent,
  };
}

function rowMixFromRow(row) {
  const defaults = defaultRowMix();
  const field = (name) => row.querySelector(`[data-strip-field="${name}"]`);
  const catchValue = field("catch_percentage")?.value;
  const baselineValue = !baselineStrategyIsActive() ? 0 : field("baseline_percentage")?.value;
  const audioValue = field("audio_tactile_percentage")?.value;
  const catchPercent = catchValue === undefined || catchValue === ""
    ? defaults.catch
    : Math.max(0, Math.min(100, Number(catchValue || 0)));
  const baselinePercent = baselineValue === undefined || baselineValue === ""
    ? defaults.baseline
    : Math.max(0, Math.min(100, Number(baselineValue || 0)));
  const audioTactilePercent = audioValue === undefined || audioValue === ""
    ? Math.max(0, 100 - catchPercent - baselinePercent)
    : Math.max(0, Math.min(100, Number(audioValue || 0)));
  return {
    audioTactile: audioTactilePercent,
    catch: catchPercent,
    baseline: baselinePercent,
    total: audioTactilePercent + catchPercent + baselinePercent,
  };
}

function applyBaselineDefaultToTrialRows() {
  const catchPercent = Math.max(0, Math.min(99, numberValue("catch-percent", 0)));
  const baselinePercent = !baselineStrategyIsActive()
    ? 0
    : Math.max(0, Math.min(99, numberValue("baseline-percent", 0)));
  for (const row of $("filmstrip-list").querySelectorAll(".filmstrip-row")) {
    const catchField = row.querySelector('[data-strip-field="catch_percentage"]');
    const baselineField = row.querySelector('[data-strip-field="baseline_percentage"]');
    const audioField = row.querySelector('[data-strip-field="audio_tactile_percentage"]');
    if (!baselineField || !audioField) continue;
    const rowCatch = catchField?.dataset.rowMixOverride === "true"
      ? Math.max(0, Math.min(99, Number(catchField.value || 0)))
      : catchPercent;
    const rowBaseline = baselineField.dataset.rowMixOverride === "true"
      ? Math.max(0, Math.min(99, Number(baselineField.value || 0)))
      : baselinePercent;
    if (catchField && catchField.dataset.rowMixOverride !== "true") catchField.value = String(rowCatch);
    if (baselineField.dataset.rowMixOverride !== "true") baselineField.value = String(rowBaseline);
    if (audioField.dataset.rowMixOverride !== "true") audioField.value = String(Math.max(1, 100 - rowCatch - rowBaseline));
  }
}

function syncCompositionSoaInputs(sourceInput) {
  const value = sourceInput?.value ?? $("soa-values").value;
  $("soa-values").value = value;
  if ($("block-soa-values") && $("block-soa-values") !== sourceInput) {
    $("block-soa-values").value = value;
  }
}

function rowExtraCount(audioCount, extraPercent, audioPercent) {
  if (audioCount <= 0 || extraPercent <= 0) return 0;
  return Math.ceil(audioCount * extraPercent / Math.max(0.1, audioPercent));
}

function rowCompositionCounts(row) {
  const audioPerBlock = rowAudioCountPerBlock(row);
  const mix = rowMixFromRow(row);
  const catchPerBlock = rowExtraCount(audioPerBlock, mix.catch, mix.audioTactile);
  const baselinePerBlock = !baselineStrategyIsActive()
    ? 0
    : rowExtraCount(audioPerBlock, mix.baseline, mix.audioTactile);
  return {
    mix,
    audioPerBlock,
    catchPerBlock,
    baselinePerBlock,
    totalPerBlock: audioPerBlock + catchPerBlock + baselinePerBlock,
  };
}

function blockCompositionEstimate() {
  const rows = [...$("filmstrip-list").querySelectorAll(".filmstrip-row")];
  if (!rows.length) {
    const soaCount = parseIntegerList($("soa-values").value).length;
    const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
    const audioPerBlock = Math.max(1, stimulusSourceDetailsFromDom().length) * Math.max(soaCount, 0) * repetitions * tactileSiteCount();
    const mix = defaultRowMix();
    const catchPerBlock = rowExtraCount(audioPerBlock, mix.catch, mix.audioTactile);
    const baselinePerBlock = !baselineStrategyIsActive()
      ? 0
      : rowExtraCount(audioPerBlock, mix.baseline, mix.audioTactile);
    return {
      audioPerBlock,
      catchPerBlock,
      baselinePerBlock,
      totalPerBlock: audioPerBlock + catchPerBlock + baselinePerBlock,
      rows: [],
    };
  }
  const composition = {
    audioPerBlock: 0,
    catchPerBlock: 0,
    baselinePerBlock: 0,
    totalPerBlock: 0,
    rows: [],
  };
  for (const row of rows) {
    const rowCounts = rowCompositionCounts(row);
    composition.audioPerBlock += rowCounts.audioPerBlock;
    composition.catchPerBlock += rowCounts.catchPerBlock;
    composition.baselinePerBlock += rowCounts.baselinePerBlock;
    composition.totalPerBlock += rowCounts.totalPerBlock;
    composition.rows.push(rowCounts);
  }
  return composition;
}

function baselineCountEstimate() {
  const strategy = currentBaselineStrategy();
  const blocks = Math.max(1, Math.round(numberValue("blocks", 1)));
  const composition = blockCompositionEstimate();
  if (!strategy || strategy === "none") {
    return { strategy, timings: [], perBlock: 0, total: 0, actualPercent: 0, audioPerBlock: composition.audioPerBlock, composition };
  }
  const timings = derivedBaselineTimingsMs(strategy);
  const perBlock = composition.baselinePerBlock;
  const denominator = Math.max(1, composition.totalPerBlock);
  return {
    strategy,
    timings,
    perBlock,
    total: perBlock * blocks,
    actualPercent: Math.round((1000 * perBlock / denominator)) / 10,
    audioPerBlock: composition.audioPerBlock,
    composition,
  };
}

function estimatedTrialSeconds() {
  const controls = currentTrajectoryControls();
  const soundWindow = controls.start_hold_s + controls.movement_duration_s + controls.end_hold_s;
  const firstStrip = state.design.protocol?.trial_strips?.[0];
  const fixedLabels = (firstStrip?.elements || [])
    .filter((element) => element.kind === "fixed_audio")
    .map((element) => element.source_label || element.label)
    .filter(Boolean);
  const fixedSeconds = fixedLabels.reduce((total, label) => {
    const clip = (state.design.prestimulus_files || []).find((item) => item.label === label);
    return total + Number(clip?.target_duration_s || 0);
  }, 0);
  return Math.max(0.1, fixedSeconds + soundWindow);
}

function updateBaselineDecision() {
  syncBaselineStrategyControls();
  const strategy = currentBaselineStrategy();
  const status = $("baseline-status");
  const soaValues = currentSoaValues();
  const customValues = parseIntegerList($("baseline-soa-values").value);
  const valid = Boolean(strategy) && soaValues.length > 0 && (strategy !== "custom" || customValues.length > 0);
  if (status) {
    status.textContent = valid ? "ready" : "required";
    status.className = `status-label ${valid ? "ready" : "required"}`;
  }
  if (strategy === "none") $("baseline-percent").value = 0;
  enforceGlobalPercentBounds("baseline-percent");
  updatePercentMixerDisplay();
  renderBaselineTactileSummary();
}

function renderTrialStrips() {
  const list = $("filmstrip-list");
  if (!list) return;
  const strips = state.design.protocol?.trial_strips || [];
  list.innerHTML = "";
  if (!strips.length) {
    list.appendChild(renderAddRowControl(-1, true));
    updateFilmstripCounts();
    return;
  }
  strips.forEach((strip, index) => {
    list.appendChild(renderTrialStripRow(strip, index));
    list.appendChild(renderAddRowControl(index, false));
  });
  updateFilmstripCounts();
}

function stripMixValues(strip = {}) {
  const protocol = state.design.protocol || {};
  const catchPercent = strip.catch_percentage ?? protocol.catch_trial_percentage ?? 0;
  const baselineFallback = protocol.include_baseline_trials === false
    ? 0
    : (protocol.baseline_trial_percentage ?? 0);
  const baselinePercent = strip.baseline_percentage ?? baselineFallback;
  const audioTactilePercent = strip.audio_tactile_percentage ?? Math.max(0, 100 - catchPercent - baselinePercent);
  return {
    audioTactile: Math.round(Number(audioTactilePercent || 0) * 10) / 10,
    catch: Math.round(Number(catchPercent || 0) * 10) / 10,
    baseline: Math.round(Number(baselinePercent || 0) * 10) / 10,
  };
}

function renderTrialStripRow(strip, index, options = {}) {
  const placeholder = Boolean(options.placeholder);
  const elements = strip.elements || [];
  const row = document.createElement("div");
  const mix = stripMixValues(strip);
  row.className = `filmstrip-row ${placeholder ? "empty-sequence-row" : ""}`;
  row.dataset.stripIndex = String(index);
  row.innerHTML = `
    ${placeholder ? "" : `
    <div class="filmstrip-row-header">
      <button type="button" class="filmstrip-preview-button" data-preview-strip="${index}" title="Prelisten trial type" aria-label="Prelisten trial type">&#9658;</button>
      <div class="filmstrip-row-actions">
        <button type="button" class="icon-action" data-strip-move="up" title="Move row up" aria-label="Move row up">^</button>
        <button type="button" class="icon-action" data-strip-move="down" title="Move row down" aria-label="Move row down">v</button>
        <button type="button" class="icon-action danger" data-remove-strip title="Remove trial sequence row" aria-label="Remove trial sequence row">x</button>
      </div>
    </div>`}
    <div class="filmstrip-row-body">
      <div class="field-row trial-condition-field">
        <label>Condition label</label>
        <input data-strip-field="label" value="${escapeAttr(strip.label || `Trial type ${index + 1}`)}">
      </div>
      <div class="filmstrip-sequence"></div>
    </div>
    <div class="filmstrip-row-mix state-only" aria-label="Trial type row composition">
      <div class="field-row">
        <label>Audio-tactile %</label>
        <input data-strip-field="audio_tactile_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.audioTactile)}">
      </div>
      <div class="field-row">
        <label>Catch %</label>
        <input data-strip-field="catch_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.catch)}">
      </div>
      <div class="field-row">
        <label>Baseline %</label>
        <input data-strip-field="baseline_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.baseline)}">
      </div>
    </div>
  `;
  const sequence = row.querySelector(".filmstrip-sequence");
  for (const [elementIndex, element] of elements.entries()) {
    sequence.appendChild(renderTrialStripElement(element, elementIndex));
    sequence.appendChild(renderAddEventControl(index, elementIndex + 1, strip));
  }
  if (!elements.length) {
    sequence.appendChild(renderAddEventControl(index, 0, strip, true));
  }
  return row;
}

function renderTrialStripElement(element, index) {
  const sourceType = element.kind === "fixed_audio" || element.kind === "jitter"
    ? element.kind
    : "looming_stimulus";
  const card = document.createElement("div");
  card.className = `filmstrip-element sequence-event ${sourceType.replace("_", "-")} ${filmstripNoiseClass(element)}`;
  card.dataset.elementIndex = String(index);
  card.dataset.elementKind = sourceType;
  if (sourceType === "fixed_audio") {
    card.innerHTML = renderFixedBlock(element);
  } else if (sourceType === "jitter") {
    card.innerHTML = renderJitterBlock(element);
  } else {
    card.innerHTML = renderAudioPoolBlock(element);
  }
  return card;
}

function renderAddEventControl(rowIndex, insertAfter, strip = {}, isEmpty = false) {
  const wrapper = document.createElement("div");
  wrapper.className = `sequence-event-add ${isEmpty ? "empty-row-add" : ""}`;
  wrapper.innerHTML = `
    <button type="button" class="sequence-event-add-symbol" data-add-strip-element="fixed_audio" data-insert-after="${insertAfter}" title="Add sequence box" aria-label="Add sequence box">+</button>
  `;
  return wrapper;
}

function renderAddRowControl(insertAfter = -1, isEmpty = false) {
  const wrapper = document.createElement("div");
  wrapper.className = `trial-row-add ${isEmpty ? "trial-row-empty" : "between-row-add"}`;
  wrapper.innerHTML = `
    <button type="button" class="sequence-event-add-symbol" data-add-strip-row data-insert-row-after="${insertAfter}" title="Add trial sequence row" aria-label="Add trial sequence row">+</button>
  `;
  return wrapper;
}

function renderFixedBlock(element) {
  return renderAudioPoolBlock(element);
}

function audioBoxLabels(element = {}) {
  const labels = (element.source_labels || []).filter(Boolean);
  if (!labels.length && element.source_label) labels.push(element.source_label);
  const fallback = String(element.label || "").trim();
  if (!labels.length && fallback && !genericAudioBoxLabel(fallback)) labels.push(fallback);
  return Array.from(new Set(labels));
}

function genericAudioBoxLabel(label = "") {
  return new Set(["Audio box", "Looming Stimulus", "Fixed audio clip", "Audio pool"]).has(String(label || "").trim());
}

function renderAudioPoolBlock(element) {
  const labels = audioBoxLabels(element);
  const title = "Audio box";
  return `
    <div class="filmstrip-element-heading">
      <span>${title}</span>
      <button type="button" class="icon-action danger" data-remove-strip-element title="Remove event" aria-label="Remove event">x</button>
    </div>
    <label class="box-mode-toggle">
      <input data-element-field="is_jitter" type="checkbox">
      Jitter / ITI box
    </label>
    <div class="sequence-label-list" data-sequence-label-list>
      ${labels.map((label) => `
        <span class="sequence-label-chip">
          <span class="sequence-label-chip-text">${escapeHtml(label)}</span>
          <span class="sequence-label-chip-actions">
            <button type="button" class="sequence-label-preview" data-preview-source-label="${escapeAttr(label)}" title="Play ${escapeAttr(label)}" aria-label="Play ${escapeAttr(label)}">&#128266;</button>
            <button type="button" class="sequence-label-remove" data-remove-box-label="${escapeAttr(label)}" title="Remove label" aria-label="Remove ${escapeAttr(label)}">x</button>
          </span>
          <input data-element-field="source_labels" type="hidden" value="${escapeAttr(label)}">
        </span>
      `).join("") || `<span class="sequence-label-empty">No labels selected</span>`}
    </div>
    <div class="box-add-label-row">
      <select data-element-field="label_picker">${sequenceAudioOptions("")}</select>
      <button type="button" data-add-box-label>Add</button>
    </div>
    <input data-element-field="label" type="hidden" value="${escapeAttr(element.label || title)}">
    <input data-element-field="randomized" type="hidden" value="true">
  `;
}

function renderJitterBlock(element) {
  const title = "Jitter / ITI event";
  const values = formatList(element.jitter_values_ms || []);
  return `
    <div class="filmstrip-element-heading">
      <span>${title}</span>
      <button type="button" class="icon-action danger" data-remove-strip-element title="Remove event" aria-label="Remove event">x</button>
    </div>
    <label class="box-mode-toggle">
      <input data-element-field="is_jitter" type="checkbox" checked>
      Jitter / ITI box
    </label>
    <div class="field-row">
      <label>Jitter values ms</label>
      <textarea data-element-field="jitter_values_ms" rows="5" autocomplete="off" placeholder="500&#10;700&#10;1100&#10;2700">${escapeHtml((element.jitter_values_ms || []).join("\n"))}</textarea>
    </div>
    <input data-element-field="label" type="hidden" value="${escapeAttr(element.label || title)}">
    <input data-element-field="randomized" type="hidden" value="true">
  `;
}

function filmstripNoiseClass(element) {
  if (element.kind === "jitter") return "jitter";
  const labels = element.source_labels || [];
  const firstLabel = labels[0] || element.source_label || "";
  const source = stimulusSourceDetailsFromDom().find((item) => item.label === firstLabel);
  return source?.noise_type ? `noise-${String(source.noise_type).toLowerCase()}` : "";
}

function fixedAudioOptions(selected = "") {
  const options = [{ value: "", label: "Select clip" }];
  for (const item of fixedAudioSourceOptions()) options.push(item);
  return renderOptionList(options, selected);
}

function sequenceAudioOptions(selected = "") {
  const options = [{ value: "", label: "Add label..." }];
  const seen = new Set();
  for (const item of fixedAudioSourceOptions()) {
    if (seen.has(item.value)) continue;
    options.push(item);
    seen.add(item.value);
  }
  for (const source of stimulusSourceDetailsFromDom()) {
    if (!source.label || seen.has(source.label)) continue;
    options.push({ value: source.label, label: source.label });
    seen.add(source.label);
  }
  return renderOptionList(options, selected);
}

function sourcePoolOptions(selected = []) {
  const selectedSet = new Set(selected || []);
  return stimulusSourceDetailsFromDom()
    .map((item) => `<option value="${escapeAttr(item.label)}" ${selectedSet.has(item.label) ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
}

function fixedAudioSourceOptions() {
  const options = [];
  for (const card of [
    ...$("audio-list").querySelectorAll(".audio-source-card"),
    ...$("snippet-list").querySelectorAll(".audio-source-card"),
  ]) {
    const role = card.querySelector('[data-field="audio_role"]')?.value;
    if (role !== "prestimulus") continue;
    const label = card.querySelector('[data-field="label"]')?.value.trim();
    if (label) options.push({ value: label, label });
  }
  return options;
}

function stimulusSourceDetailsFromDom() {
  const sources = [];
  for (const card of $("noise-list").querySelectorAll(".noise-source-card")) {
    const label = card.querySelector('[data-field="label"]')?.value.trim() || "Generated noise";
    sources.push({
      label,
      noise_type: card.querySelector('[data-field="noise_type"]')?.value || "pink",
    });
  }
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const role = card.querySelector('[data-field="audio_role"]')?.value;
    if (role === "prestimulus") continue;
    const label = card.querySelector('[data-field="label"]')?.value.trim() || audioRoleTitle(role);
    sources.push({ label, noise_type: card.querySelector('[data-field="tone_type"]')?.value || "custom_audio" });
  }
  return sources;
}

function collectTrialStrips() {
  const strips = [];
  for (const [stripIndex, row] of [...$("filmstrip-list").querySelectorAll(".filmstrip-row")].entries()) {
    const label = row.querySelector('[data-strip-field="label"]')?.value.trim() || `Trial type ${stripIndex + 1}`;
    const elements = [];
    for (const [elementIndex, card] of [...row.querySelectorAll(".filmstrip-element")].entries()) {
      const kind = card.dataset.elementKind === "fixed_audio" || card.dataset.elementKind === "jitter"
        ? card.dataset.elementKind
        : "looming_stimulus";
      const item = {
        element_id: `row-${stripIndex + 1}-element-${elementIndex + 1}`,
        kind,
        label: card.querySelector('[data-element-field="label"]')?.value.trim() || (kind === "fixed_audio" ? "Fixed audio clip" : kind === "jitter" ? "Jitter / ITI event" : "Looming Stimulus"),
        source_label: "",
        source_labels: [],
        jitter_values_ms: [],
        randomized: Boolean(card.querySelector('[data-element-field="randomized"]')?.checked),
      };
      if (kind === "fixed_audio") {
        item.source_labels = [...card.querySelectorAll('input[data-element-field="source_labels"]')].map((input) => input.value).filter(Boolean);
        item.source_label = item.source_labels[0] || "";
        item.label = item.source_labels.length > 1 ? "Audio pool" : (item.source_label || item.label);
      } else if (kind === "jitter") {
        item.jitter_values_ms = parseIntegerList(card.querySelector('[data-element-field="jitter_values_ms"]')?.value).filter((value) => value >= 0);
        item.randomized = true;
      } else {
        const checked = [...card.querySelectorAll('input[data-element-field="source_labels"]:checked')].map((input) => input.value);
        const hidden = [...card.querySelectorAll('input[data-element-field="source_labels"][type="hidden"]')].map((input) => input.value);
        const selected = [...card.querySelectorAll('select[data-element-field="source_labels"] option:checked')].map((option) => option.value);
        item.source_labels = (hidden.length ? hidden : (checked.length ? checked : selected)).filter(Boolean);
        item.source_label = item.source_labels[0] || "";
        item.randomized = true;
      }
      elements.push(item);
    }
    strips.push({
      strip_id: `strip-${stripIndex + 1}`,
      label,
      audio_tactile_percentage: Number(row.querySelector('[data-strip-field="audio_tactile_percentage"]')?.value || 0),
      catch_percentage: Number(row.querySelector('[data-strip-field="catch_percentage"]')?.value || 0),
      baseline_percentage: Number(row.querySelector('[data-strip-field="baseline_percentage"]')?.value || 0),
      elements,
    });
  }
  return strips;
}

function updateFilmstripCounts() {
  for (const row of $("filmstrip-list").querySelectorAll(".filmstrip-row")) {
    const rowCounts = rowCompositionCounts(row);
    const mixValid = Math.abs(rowCounts.mix.total - 100) <= 0.5 && rowCounts.mix.audioTactile > 0;
    row.classList.toggle("mix-warning", !mixValid);
  }
  renderProtocolSummary();
  renderLiveTrialPreviewTables();
  updateBaselineDecision();
  renderBakePanel();
}

async function previewFilmstripRow(button) {
  const row = button.closest(".filmstrip-row");
  if (!row) return;
  state.design.protocol = state.design.protocol || {};
  state.design.protocol.trial_strips = collectTrialStrips();
  const payload = collectPayload();
  payload.strip_index = Number(row.dataset.stripIndex || 0);
  button.disabled = true;
  button.classList.add("playing");
  let started = false;
  try {
    const preview = await api("/api/trials/preview-row", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    if (activeTrialRowPreviewAudio) {
      activeTrialRowPreviewAudio.pause();
      activeTrialRowPreviewAudio = null;
    }
    const audio = new Audio(apiUrl(`${preview.url}?v=${Date.now()}`));
    activeTrialRowPreviewAudio = audio;
    audio.addEventListener("ended", () => button.classList.remove("playing"), { once: true });
    audio.addEventListener("pause", () => button.classList.remove("playing"), { once: true });
    await audio.play();
    started = true;
    showToast(`Preview: ${preview.sequence.join(" | ")}`);
  } catch (error) {
    button.classList.remove("playing");
    throw error;
  } finally {
    if (!started) button.classList.remove("playing");
    button.disabled = false;
  }
}

async function previewSourceLabel(button) {
  const label = button.dataset.previewSourceLabel || "";
  if (!label) return;
  state.design.protocol = state.design.protocol || {};
  state.design.protocol.trial_strips = collectTrialStrips();
  const payload = collectPayload();
  payload.label = label;
  button.disabled = true;
  button.classList.add("playing");
  const audioContext = getSourcePreviewAudioContext();
  const contextReady = audioContext?.resume().catch(() => {});
  let started = false;
  try {
    const preview = await api("/api/audio/preview-source", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    button.disabled = false;
    await playSourcePreviewAudio(
      apiUrl(`${preview.url}?v=${Date.now()}`),
      button,
      audioContext,
      contextReady,
      Number(preview.duration_s) || 0
    );
    started = true;
    showToast(`Soundcheck: ${preview.label || label}`);
  } catch (error) {
    button.classList.remove("playing");
    throw error;
  } finally {
    if (!started) button.classList.remove("playing");
    button.disabled = false;
  }
}

function getSourcePreviewAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!sourcePreviewAudioContext) {
    sourcePreviewAudioContext = new AudioContextClass();
  }
  return sourcePreviewAudioContext;
}

function stopActiveSourcePreview() {
  const previousButton = activeSourcePreviewButton;
  if (activeSourcePreviewNode) {
    try {
      activeSourcePreviewNode.stop();
    } catch (_error) {
      // Already stopped.
    }
    activeSourcePreviewNode.disconnect();
    activeSourcePreviewNode = null;
  }
  if (activeSourcePreviewAudio) {
    activeSourcePreviewAudio.pause();
    activeSourcePreviewAudio = null;
  }
  finishSourcePreview(previousButton);
}

function finishSourcePreview(button = activeSourcePreviewButton) {
  if (activeSourcePreviewClearTimer) {
    clearTimeout(activeSourcePreviewClearTimer);
    activeSourcePreviewClearTimer = null;
  }
  if (button) button.classList.remove("playing");
  if (!button || activeSourcePreviewButton === button) {
    activeSourcePreviewButton = null;
  }
}

function armSourcePreviewCleanup(button, durationS) {
  const durationMs = Number.isFinite(durationS) && durationS > 0
    ? Math.min(Math.max(durationS * 1000 + 750, 1250), 60000)
    : 15000;
  activeSourcePreviewButton = button;
  activeSourcePreviewClearTimer = window.setTimeout(() => {
    if (activeSourcePreviewButton !== button) return;
    if (activeSourcePreviewNode) {
      try {
        activeSourcePreviewNode.stop();
      } catch (_error) {
        // Already stopped.
      }
      activeSourcePreviewNode.disconnect();
      activeSourcePreviewNode = null;
    }
    if (activeSourcePreviewAudio) {
      activeSourcePreviewAudio.pause();
      activeSourcePreviewAudio = null;
    }
    finishSourcePreview(button);
  }, durationMs);
}

async function playSourcePreviewAudio(url, button, audioContext, contextReady, durationS = 0) {
  stopActiveSourcePreview();
  armSourcePreviewCleanup(button, durationS);
  if (audioContext) {
    if (contextReady) await Promise.race([contextReady, delay(250)]);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Preview audio unavailable: ${response.status}`);
    const buffer = await audioContext.decodeAudioData(await response.arrayBuffer());
    const node = audioContext.createBufferSource();
    node.buffer = buffer;
    node.connect(audioContext.destination);
    activeSourcePreviewNode = node;
    node.addEventListener("ended", () => {
      if (activeSourcePreviewNode === node) {
        activeSourcePreviewNode = null;
      }
      node.disconnect();
      finishSourcePreview(button);
    }, { once: true });
    node.start();
    return;
  }
  const audio = new Audio(url);
  activeSourcePreviewAudio = audio;
  audio.addEventListener("ended", () => {
    if (activeSourcePreviewAudio === audio) {
      activeSourcePreviewAudio = null;
    }
    finishSourcePreview(button);
  }, { once: true });
  audio.addEventListener("pause", () => {
    if (activeSourcePreviewAudio === audio) {
      activeSourcePreviewAudio = null;
    }
    finishSourcePreview(button);
  }, { once: true });
  audio.play().catch((error) => {
    finishSourcePreview(button);
    showToast(error.message || String(error));
  });
}

function setTrialStrips(strips) {
  state.design.protocol = state.design.protocol || {};
  state.design.protocol.trial_strips = strips;
  renderTrialStrips();
}

function defaultTrialStrip(rowNumber, kind = null) {
  const mix = defaultRowMix();
  return {
    strip_id: `strip-${rowNumber}`,
    label: `Trial type ${rowNumber}`,
    audio_tactile_percentage: mix.audioTactile,
    catch_percentage: mix.catch,
    baseline_percentage: mix.baseline,
    elements: kind ? [defaultFilmstripElement(kind)] : [],
  };
}

function addFilmstripRow(kind = null, insertAfter = "end") {
  const strips = collectTrialStrips();
  const rawInsertAfter = insertAfter === undefined || insertAfter === null ? "end" : insertAfter;
  const targetIndex = rawInsertAfter === "end"
    ? strips.length
    : Math.max(0, Math.min(strips.length, Number(rawInsertAfter) + 1));
  strips.splice(targetIndex, 0, defaultTrialStrip(targetIndex + 1, kind || "fixed_audio"));
  setTrialStrips(strips);
}

function defaultFilmstripElement(kind) {
  if (kind === "fixed_audio") {
    return {
      element_id: "",
      kind: "fixed_audio",
      label: "Audio box",
      source_label: "",
      source_labels: [],
      randomized: true,
    };
  }
  if (kind === "jitter") {
    return {
      element_id: "",
      kind: "jitter",
      label: "Jitter / ITI event",
      source_label: "",
      source_labels: [],
      jitter_values_ms: [],
      randomized: true,
    };
  }
  return {
    element_id: "",
    kind: "looming_stimulus",
    label: "Audio box",
    source_label: "",
    source_labels: [],
    randomized: true,
  };
}

function addFilmstripElement(button, kind) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const strips = collectTrialStrips();
  if (!strips[stripIndex]) return;
  const insertAfter = Number(button.dataset.insertAfter ?? strips[stripIndex].elements.length);
  const index = Math.max(0, Math.min(strips[stripIndex].elements.length, insertAfter));
  strips[stripIndex].elements.splice(index, 0, defaultFilmstripElement(kind));
  setTrialStrips(strips);
}

function removeFilmstripRow(button) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const strips = collectTrialStrips();
  if (stripIndex < 0) return;
  strips.splice(stripIndex, 1);
  setTrialStrips(strips);
}

function moveFilmstripRow(button, direction) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const targetIndex = direction === "up" ? stripIndex - 1 : stripIndex + 1;
  const strips = collectTrialStrips();
  if (!strips[stripIndex] || !strips[targetIndex]) return;
  const [item] = strips.splice(stripIndex, 1);
  strips.splice(targetIndex, 0, item);
  setTrialStrips(strips);
}

function removeFilmstripElement(button) {
  const row = button.closest(".filmstrip-row");
  const card = button.closest(".filmstrip-element");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const elementIndex = Number(card?.dataset.elementIndex || -1);
  const strips = collectTrialStrips();
  if (!strips[stripIndex] || elementIndex < 0) return;
  strips[stripIndex].elements.splice(elementIndex, 1);
  setTrialStrips(strips);
}

function addBoxLabel(button) {
  const row = button.closest(".filmstrip-row");
  const card = button.closest(".filmstrip-element");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const elementIndex = Number(card?.dataset.elementIndex || -1);
  const label = card?.querySelector('[data-element-field="label_picker"]')?.value || "";
  if (!label) return;
  const strips = collectTrialStrips();
  const element = strips[stripIndex]?.elements?.[elementIndex];
  if (!element) return;
  const labels = audioBoxLabels(element);
  if (!labels.includes(label)) labels.push(label);
  element.kind = "fixed_audio";
  element.source_label = labels[0] || "";
  element.source_labels = labels;
  element.label = labels.length > 1 ? "Audio pool" : (labels[0] || "Audio box");
  setTrialStrips(strips);
}

function removeBoxLabel(button) {
  const row = button.closest(".filmstrip-row");
  const card = button.closest(".filmstrip-element");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const elementIndex = Number(card?.dataset.elementIndex || -1);
  const label = button.dataset.removeBoxLabel || "";
  const strips = collectTrialStrips();
  const element = strips[stripIndex]?.elements?.[elementIndex];
  if (!element) return;
  const labels = audioBoxLabels(element).filter((item) => item !== label);
  element.kind = "fixed_audio";
  element.source_label = labels[0] || "";
  element.source_labels = labels;
  element.label = labels.length > 1 ? "Audio pool" : (labels[0] || "Audio box");
  setTrialStrips(strips);
}

function setFilmstripElementMode(input) {
  const row = input.closest(".filmstrip-row");
  const card = input.closest(".filmstrip-element");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const elementIndex = Number(card?.dataset.elementIndex || -1);
  const strips = collectTrialStrips();
  const element = strips[stripIndex]?.elements?.[elementIndex];
  if (!element) return;
  if (input.checked) {
    strips[stripIndex].elements[elementIndex] = {
      element_id: element.element_id || "",
      kind: "jitter",
      label: "Jitter / ITI event",
      source_label: "",
      source_labels: [],
      jitter_values_ms: element.jitter_values_ms || [],
      randomized: true,
    };
  } else {
    strips[stripIndex].elements[elementIndex] = {
      element_id: element.element_id || "",
      kind: "fixed_audio",
      label: "Audio box",
      source_label: "",
      source_labels: audioBoxLabels(element),
      jitter_values_ms: [],
      randomized: true,
    };
  }
  setTrialStrips(strips);
}

function syncFilmstripSourceOptions() {
  for (const select of document.querySelectorAll('[data-element-field="source_label"]')) {
    const selected = select.value;
    select.innerHTML = fixedAudioOptions(selected);
    select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
  }
  for (const select of document.querySelectorAll('[data-element-field="label_picker"]')) {
    const selected = select.value;
    select.innerHTML = sequenceAudioOptions(selected);
    select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
  }
  for (const select of document.querySelectorAll('[data-element-field="source_labels"]')) {
    const selected = [...select.selectedOptions].map((option) => option.value);
    select.innerHTML = sourcePoolOptions(selected);
  }
  updateFilmstripCounts();
}

function renderRun() {
  const setup = state.run_sequence_setup || {};
  const segment6 = projectSegment("6_experiment_run_setup");
  const prepared = Boolean(setup.prepared || segment6.status === "ready");
  if ($("participants") && document.activeElement !== $("participants")) {
    $("participants").value = state.design.protocol?.participants ?? setup.participant_count ?? 1;
  }
  for (const input of document.querySelectorAll('input[name="experiment-structure"]')) {
    if (document.activeElement !== input) input.checked = input.value === (setup.experiment_structure || "single");
    input.disabled = prepared;
  }
  if ($("participants")) $("participants").disabled = prepared;
  const pill = $("run-sequence-status");
  if (pill) {
    pill.textContent = prepared ? "prepared" : setup.ready ? "preview" : "required";
    pill.className = `status-label ${prepared || setup.ready ? "ready" : "required"}`;
  }
  const regenerateButton = $("regenerate-run-sequence");
  if (regenerateButton) regenerateButton.disabled = prepared || !setup.ready;
  const prepareButton = $("prepare-experiment");
  if (prepareButton) {
    prepareButton.disabled = !setup.ready && !isProfileReadonlyMode();
    prepareButton.textContent = prepared ? "Open Experiment Runner" : "Save Design and Start Experiment Runner";
  }
  const summary = $("run-sequence-summary");
  if (summary) {
    const participantCount = Number(setup.participant_count || state.design.protocol?.participants || 0);
    const partCount = Number(setup.parts_per_participant || (currentExperimentStructure() === "pre_post" ? 2 : 1));
    const blockRuns = Number(setup.total_block_runs || 0);
    summary.textContent = setup.ready
      ? `${participantCount} participants / ${partCount} ${partCount === 1 ? "part" : "parts"} / ${blockRuns} block runs`
      : (setup.message || "waiting for accepted blocks");
    summary.className = `status-label ${setup.ready ? "ready" : "required"}`;
  }
  renderRunInstructions(setup.instruction_profile || state.design?.study_profile_reference_parameters?.dashboard_run_setup?.instruction_profile || {});
  renderRunSequenceTable(setup.rows || []);
  renderProtocolSummary();
}

function normalizedRunInstructionSlots(profile = {}) {
  const rawSlots = Array.isArray(profile.slots) ? profile.slots : [];
  const bySlot = new Map(rawSlots.map((item) => [item.slot, item]));
  return RUN_INSTRUCTION_SLOTS.map((definition) => {
    const item = bySlot.get(definition.slot) || {};
    const mode = RUN_INSTRUCTION_CONTINUE_MODES.some((entry) => entry.value === item.continue_mode)
      ? item.continue_mode
      : "click";
    return {
      slot: definition.slot,
      label: item.label || definition.label,
      enabled: Boolean(item.enabled),
      required: false,
      path: item.path || "",
      duration_s: Number(item.duration_s || 0),
      sample_rate: Number(item.sample_rate || 0),
      channels: Number(item.channels || 0),
      sha256: item.sha256 || "",
      continue_mode: mode,
      delay_s: Math.max(0, Number(item.delay_s || 0)),
      button_label: item.button_label || "Continue",
      source: item.source || ""
    };
  });
}

function renderRunInstructions(profile = {}) {
  const container = $("run-instruction-slots");
  if (!container) return;
  const setup = state.run_sequence_setup || {};
  const prepared = Boolean(setup.prepared || projectSegment("6_experiment_run_setup").status === "ready");
  const slots = normalizedRunInstructionSlots(profile);
  const enabledCount = slots.filter((slot) => slot.enabled && slot.path).length;
  const summary = $("run-instructions-summary");
  if (summary) {
    summary.textContent = enabledCount ? `${enabledCount} of ${slots.length} optional clips enabled` : "optional";
    summary.className = `status-label ${enabledCount ? "ready" : "optional"}`;
  }
  container.innerHTML = slots.map((slot) => {
    const duration = slot.duration_s ? `${slot.duration_s.toFixed(slot.duration_s >= 10 ? 1 : 2)}s` : "no clip";
    const modeOptions = RUN_INSTRUCTION_CONTINUE_MODES.map((mode) => (
      `<option value="${mode.value}" ${mode.value === slot.continue_mode ? "selected" : ""}>${mode.label}</option>`
    )).join("");
    return `
      <article class="run-instruction-slot" data-run-instruction-slot="${escapeHtml(slot.slot)}">
        <label class="inline-toggle">
          <input type="checkbox" data-instruction-field="enabled" ${slot.enabled ? "checked" : ""} ${prepared ? "disabled" : ""}>
          <span>${escapeHtml(RUN_INSTRUCTION_SLOTS.find((item) => item.slot === slot.slot)?.label || slot.slot)}</span>
        </label>
        <input class="instruction-label-input" data-instruction-field="label" type="text" value="${escapeHtml(slot.label)}" ${prepared ? "disabled" : ""}>
        <button type="button" class="instruction-import-button" data-instruction-import="${escapeHtml(slot.slot)}" ${prepared ? "disabled" : ""}>Load Audio</button>
        <span class="status-label ${slot.path ? "ready" : "optional"}">${escapeHtml(duration)}</span>
        <select data-instruction-field="continue_mode" ${prepared ? "disabled" : ""}>${modeOptions}</select>
        <input data-instruction-field="delay_s" type="number" min="0" step="0.1" value="${slot.delay_s}" ${prepared ? "disabled" : ""} title="Delay seconds">
        <input data-instruction-field="button_label" type="text" value="${escapeHtml(slot.button_label)}" ${prepared ? "disabled" : ""} title="Runner button label">
        <input data-instruction-field="path" type="hidden" value="${escapeHtml(slot.path)}">
        <input data-instruction-field="duration_s" type="hidden" value="${slot.duration_s}">
        <input data-instruction-field="sample_rate" type="hidden" value="${slot.sample_rate}">
        <input data-instruction-field="channels" type="hidden" value="${slot.channels}">
        <input data-instruction-field="sha256" type="hidden" value="${escapeHtml(slot.sha256)}">
        <input data-instruction-field="source" type="hidden" value="${escapeHtml(slot.source)}">
      </article>
    `;
  }).join("");
}

function collectRunInstructionProfile() {
  const slots = [];
  for (const definition of RUN_INSTRUCTION_SLOTS) {
    const card = document.querySelector(`[data-run-instruction-slot="${definition.slot}"]`);
    const field = (name) => card?.querySelector(`[data-instruction-field="${name}"]`);
    slots.push({
      slot: definition.slot,
      label: field("label")?.value.trim() || definition.label,
      enabled: field("enabled")?.checked === true,
      required: false,
      path: field("path")?.value.trim() || "",
      duration_s: Number(field("duration_s")?.value || 0),
      sample_rate: Number(field("sample_rate")?.value || 0),
      channels: Number(field("channels")?.value || 0),
      sha256: field("sha256")?.value.trim() || "",
      continue_mode: field("continue_mode")?.value || "click",
      delay_s: Math.max(0, Number(field("delay_s")?.value || 0)),
      button_label: field("button_label")?.value.trim() || "Continue",
      source: field("source")?.value.trim() || ""
    });
  }
  return { schema: "pps-run-instructions.v1", slots };
}

function renderWorkflow() {
  const workflow = state.custom_workflow || { is_custom: false, steps: [] };
  const customMode = Boolean(workflow.is_custom);
  const profileReadonly = isProfileReadonlyMode();
  document.body.classList.toggle("custom-mode", customMode);
  document.body.classList.toggle("profile-readonly-mode", profileReadonly);
  const pill = $("workflow-pill");
  const activeStep = workflow.current_step || "run";
  const activeIndex = WORKFLOW_STEPS.indexOf(activeStep);
  const unlockedIndex = customMode && activeIndex >= 0 ? activeIndex : WORKFLOW_STEPS.length - 1;

  pill.textContent = customMode
    ? workflow.ready_to_prepare ? "custom ready" : `${stepLabel(activeStep)} required`
    : "profile loaded";
  pill.className = `status-label ${customMode && !workflow.ready_to_prepare ? "required" : "ready"}`;

  const stepMap = new Map((workflow.steps || []).map((step) => [step.id, step]));
  for (const stepId of WORKFLOW_STEPS) {
    const index = WORKFLOW_STEPS.indexOf(stepId);
    const step = customMode
      ? (stepMap.get(stepId) || { id: stepId, complete: false, missing: [] })
      : profileStepStatus(stepId);
    const locked = Boolean(customMode && index > unlockedIndex);
    const current = Boolean(customMode && stepId === activeStep);
    const complete = Boolean(step.complete);
    const link = document.querySelector(`[data-step-link="${stepId}"]`);
    const stateLabel = document.querySelector(`[data-step-state="${stepId}"]`);
    const badges = document.querySelectorAll(`[data-step-badge="${stepId}"]`);

    if (link) {
      link.classList.toggle("locked", locked);
      link.classList.toggle("current", current);
      link.classList.toggle("complete", complete);
      link.classList.toggle("not-ready", !complete);
      link.setAttribute("aria-disabled", String(locked));
    }
    if (stateLabel) {
      const label = step.label || humanize(stepId);
      const missing = Array.isArray(step.missing) && step.missing.length
        ? `: ${step.missing.join(" ")}`
        : "";
      const status = complete ? "ready" : "not ready";
      stateLabel.textContent = complete ? "\u2713" : "X";
      stateLabel.className = `decision-state ${complete ? "ready" : "not-ready"}`;
      stateLabel.title = `${label} ${status}${missing}`;
      stateLabel.setAttribute("aria-label", `${label} ${status}`);
    }
    for (const badge of badges) {
      badge.textContent = profileReadonly ? "read-only" : locked ? "locked" : complete ? "ready" : "required";
      badge.className = `step-badge ${profileReadonly ? "readonly" : locked ? "locked" : complete ? "complete" : current ? "current" : ""}`;
    }
  }

  for (const panel of document.querySelectorAll("[data-step-panel]")) {
    const stepId = panel.dataset.stepPanel;
    const locked = Boolean(customMode && WORKFLOW_STEPS.indexOf(stepId) > unlockedIndex);
    const readonly = Boolean(profileReadonly && stepId !== "study");
    panel.classList.toggle("locked", locked);
    panel.classList.toggle("profile-readonly", readonly);
    if (readonly) {
      panel.title = "Create a custom study before editing this loaded profile.";
    } else if (panel.title === "Create a custom study before editing this loaded profile.") {
      panel.title = "";
    }
    for (const control of panel.querySelectorAll("input, select, button")) {
      const readonlyLocked = readonly && !profileReadonlyControlAllowed(control);
      if (readonlyLocked) {
        if (!control.title) {
          control.dataset.profileReadonlyTitle = "true";
          control.title = "Create a custom study before editing this loaded profile.";
        }
      } else if (control.dataset.profileReadonlyTitle === "true") {
        control.title = "";
        delete control.dataset.profileReadonlyTitle;
      }
      setWorkflowDisabled(control, locked || readonlyLocked);
    }
  }

  setWorkflowDisabled($("design-name"), profileReadonly);
  setWorkflowDisabled($("apply-profile-project"), profileReadonly);
  setWorkflowDisabled($("apply-design"), profileReadonly);
  updateActiveNav();
}

function renderPreviewTables() {
  renderTrialPreviewTable(state.trial_preview || []);
}

function renderRunSequenceTable(rows) {
  fillTable("run-sequence-table", rows, ["participant", "part", "block_count", "block_order"]);
}

function renderTrialPreviewTable(trialRows, totalRows = trialRows.length) {
  const count = $("trial-count");
  const table = $("trial-table");
  if (!count || !table) return;
  const visibleCount = trialRows.length;
  count.textContent = totalRows > visibleCount
    ? `${visibleCount} of ${totalRows} shown`
    : `${visibleCount} shown`;
  fillTable("trial-table", trialRows, ["index", "family", "row", "folder", "file", "repetition", "duration", "soa_ms", "sequence"]);
}

function cartesianProduct(factors) {
  return factors.reduce((acc, factor) => acc.flatMap((prefix) => factor.map((choice) => [...prefix, choice])), [[]]);
}

function stripPreviewVariants(strip) {
  const factors = [];
  for (const element of strip.elements || []) {
    if (element.kind === "jitter") {
      const values = (element.jitter_values_ms || []).filter((value) => Number.isFinite(Number(value)));
      factors.push(values.map((value) => ({
        kind: "jitter",
        label: `${element.label || "Jitter"} (${value} ms)`,
        value,
      })));
    } else {
      const labels = audioBoxLabels(element);
      factors.push(labels.map((label) => ({ kind: "audio", label })));
    }
  }
  if (!factors.length || factors.some((factor) => !factor.length)) return [];
  return cartesianProduct(factors);
}

function previewVariantLabel(variant, family = "Audio-Tactile") {
  const labels = variant.map((choice) => family === "Baseline" && choice.kind === "audio" ? "Baseline tactile" : choice.label);
  if (family === "Baseline" && !labels.includes("Baseline tactile")) labels.push("Baseline tactile");
  return labels.join(" | ");
}

function previewVariantKey(variant) {
  return variant.map((choice) => choice.kind === "jitter" ? `jitter_${choice.value}ms` : choice.label).join(" + ");
}

function renderLiveTrialPreviewTables() {
  if (!state?.design?.protocol || !$("trial-table")) return;
  const pool = trialPoolCompositionEstimate();
  const rows = [];
  const pushRow = (row) => {
    if (rows.length < TRIAL_PREVIEW_LIMIT) rows.push(row);
  };
  let index = 1;
  for (const group of pool.groups) {
    for (const file of group.files) {
      const reps = repetitionForFile(file);
      for (let repetition = 1; repetition <= reps; repetition += 1) {
        pushRow({
          index,
          family: familyDisplayName(file.family),
          row: file.row_label || file.row_folder_name || "",
          folder: file.folder_name || group.folderName,
          file: file.source_file_name || "",
          repetition,
          duration: formatDurationMs(file.duration_ms || 0),
          soa_ms: file.soa_ms ?? "",
          sequence: file.sequence_labels || file.sequence_variant_key || "",
        });
        index += 1;
      }
    }
  }
  if (!pool.groups.length) {
    renderTrialPreviewTable([], 0);
    return;
  }
  renderTrialPreviewTable(rows, pool.totalTrials);
}

function fillTable(id, rows, keys) {
  const table = $(id);
  const body = table?.querySelector("tbody");
  if (!body) return;
  body.innerHTML = "";
  for (const row of rows) {
    const tr = body.insertRow();
    const family = String(row.type || row.trial_type || "").toLowerCase();
    if (family.includes("baseline")) tr.classList.add("preview-baseline");
    else if (family.includes("catch")) tr.classList.add("preview-catch");
    else if (family.includes("audio")) tr.classList.add("preview-audio");
    for (const key of keys) {
      const cell = tr.insertCell();
      cell.textContent = row[key] ?? "";
    }
  }
}

function renderJob(job) {
  const detail = job.result ? JSON.stringify(job.result, null, 2) : (job.error || job.message || "");
  return `
    <div class="job-item">
      <strong><span>${humanize(job.kind)}</span><span>${job.status}</span></strong>
      <div class="muted">${job.message || ""}</div>
      ${detail ? `<pre>${escapeHtml(detail)}</pre>` : ""}
    </div>
  `;
}

function collectPayload() {
  const design = clone(state.design);
  const trajectoryControls = currentTrajectoryControls();
  design.name = $("design-name").value.trim() || "Untitled PPS design";
  design.noises = collectNoises();
  const audio = collectAudioFiles();
  design.custom_looming_files = audio.looming;
  design.prestimulus_files = audio.prestimulus;
  const trialStrips = collectTrialStrips();
  const legacySpatial = design.protocol?.spatial_values_cm?.length
    ? design.protocol.spatial_values_cm
    : [trajectoryControls.end_distance_cm];
  const baselineStrategy = currentBaselineStrategy();
  const baselineTimings = baselineStrategy === "custom"
    ? parseIntegerList($("baseline-soa-values").value)
    : [];
  design.protocol = {
    ...(design.protocol || {}),
    repetitions_per_condition: Math.max(1, Math.round(numberValue("repetitions", 1))),
    soa_values_ms: parseIntegerList($("block-soa-values").value || $("soa-values").value),
    spatial_values_cm: legacySpatial,
    pair_spatial_values_with_soas: false,
    include_catch_trials: $("include-catch-trials")?.checked || false,
    catch_trial_percentage: numberValue("catch-percent", 0),
    include_baseline_trials: baselineStrategyIsActive(baselineStrategy),
    baseline_strategy: baselineStrategy,
    baseline_trial_percentage: baselineStrategyIsActive(baselineStrategy) ? numberValue("baseline-percent", 0) : 0,
    baseline_soa_values_ms: baselineTimings,
    baseline_custom_trial_mode: $("baseline-custom-audio-tactile")?.checked ? "audio_tactile" : "tactile_only",
    blocks: Math.max(1, Math.round(numberValue("block-count", numberValue("blocks", 1)))),
    participants: Math.max(1, Math.round(numberValue("participants", 1))),
    trial_strips: trialStrips
  };
  return {
    participant_id: state.participant_id || (state.custom_workflow?.is_custom ? "" : "P001"),
    design,
    trajectory_controls: trajectoryControls,
    run_setup: {
      experiment_structure: currentExperimentStructure(),
      seed: state.run_sequence_setup?.seed || state.design?.study_profile_reference_parameters?.dashboard_run_setup?.seed || 0,
      instruction_profile: collectRunInstructionProfile(),
    }
  };
}

function collectProfileRunPayload() {
  return {
    participant_id: state.participant_id || "P001"
  };
}

function currentExperimentStructure() {
  return document.querySelector('input[name="experiment-structure"]:checked')?.value || state.run_sequence_setup?.experiment_structure || "single";
}

function collectNoises() {
  return [...$("noise-list").querySelectorAll(".noise-source-card")].map((card) => {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    return {
      label: field("label").value.trim() || "Noise",
      noise_type: field("noise_type").value,
      azimuth_deg: Number(field("azimuth_deg").value || 0),
      elevation_deg: Number(field("elevation_deg").value || 0),
      gain: Number(field("gain").value || 1),
      prebaked_path: field("prebaked_path")?.value.trim() || "",
      trajectory_snapshot: readJsonField(field("trajectory_snapshot"))
    };
  });
}

function collectAudioFiles() {
  const result = { looming: [], prestimulus: [] };
  const cards = [
    ...$("audio-list").querySelectorAll(".audio-source-card"),
    ...$("snippet-list").querySelectorAll(".audio-source-card"),
  ];
  for (const card of cards) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const role = field("audio_role").value;
    const item = {
      label: field("label").value.trim() || "Audio file",
      path: field("path").value.trim(),
      target_duration_s: Number(field("target_duration_s").value || 4),
      render_mode: role === "spatialize" ? "spatialize" : "preserve",
      tone_type: field("tone_type")?.value.trim() || "",
      gain: Number(field("gain").value || 1),
      placement: normalizeSnippetPlacement(field("placement")?.value),
      target_source_label: field("target_source_label")?.value.trim() || "",
      phase: field("phase")?.value.trim() || "",
      gap_s: Math.max(0, Number(field("gap_s")?.value || 0)),
      motion_mode: field("motion_mode")?.value || (role === "prestimulus" ? "stationary" : "looming"),
      trajectory_snapshot: readJsonField(field("trajectory_snapshot"))
    };
    if (role === "prestimulus") {
      result.prestimulus.push(item);
    } else {
      result.looming.push(item);
    }
  }
  return result;
}

async function applyDesign() {
  if (!ensureEditableProject()) return;
  state = await api("/api/design", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
  updateViewer();
  const staleSegments = Object.values(state.project_segments || {}).filter((segment) => segment.status === "stale");
  showToast(staleSegments.length ? "Design saved; downstream segments need rebake" : "Design saved");
}

async function continueWorkflowStep(stepId) {
  if (!ensureEditableProject()) return;
  state = await api("/api/design", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
  updateViewer();
  const step = getWorkflowStep(stepId);
  if (!step || step.complete) {
    const next = NEXT_STEP[stepId];
    if (next) {
      scrollToStep(next);
    }
    showToast("Step saved");
    return;
  }
  showToast(step.missing.join(" "));
  scrollToStep(stepId);
}

async function loadTemplate() {
  if (templateLoadInFlight) return;
  const select = $("template-select");
  const id = select.value;
  if (!id) return;
  templateLoadInFlight = true;
  select.disabled = true;
  try {
    state = await api(`/api/templates/${encodeURIComponent(id)}/load`, { method: "POST" });
    renderAll();
    updateViewer();
    showToast(id === CUSTOM_TEMPLATE_ID ? "Custom design started" : "Profile loaded");
  } finally {
    templateLoadInFlight = false;
    $("template-select").disabled = false;
  }
}

async function loadCustomProject() {
  const select = $("existing-custom-project");
  const projectId = select?.value || "";
  if (!projectId) {
    showToast("Choose a custom study to open");
    return;
  }
  state = await api(`/api/projects/${encodeURIComponent(projectId)}/load`, { method: "POST" });
  renderAll();
  updateViewer();
  showToast("Custom study opened");
  scrollToStep(state.custom_workflow?.current_step || "study");
}

function openSegmentInfoModal(stepId, trigger = null) {
  const info = SEGMENT_INFO[stepId];
  if (!info) return;
  segmentInfoModalReturnFocus = trigger instanceof HTMLElement
    ? trigger
    : (document.activeElement instanceof HTMLElement ? document.activeElement : null);
  $("segment-info-kicker").textContent = info.kicker;
  $("segment-info-modal-title").textContent = info.title;
  $("segment-info-purpose").textContent = info.purpose;
  $("segment-info-inputs").textContent = info.inputs;
  $("segment-info-backend").textContent = info.backend;
  $("segment-info-next").textContent = info.next;
  $("segment-info-modal").hidden = false;
  document.body.classList.add("modal-open");
  window.setTimeout(() => $("segment-info-modal-close")?.focus(), 0);
}

function closeSegmentInfoModal() {
  const modal = $("segment-info-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  if (segmentInfoModalReturnFocus && document.contains(segmentInfoModalReturnFocus)) {
    segmentInfoModalReturnFocus.focus();
  }
  segmentInfoModalReturnFocus = null;
}

function defaultCustomStudyName() {
  return `${state?.design?.name || state?.design?.study_profile_title || "PPS design"} custom`;
}

function openCustomizeModal() {
  if (!state || !isProfileReadonlyMode()) return;
  const modal = $("customize-modal");
  const input = $("customize-study-name");
  const source = $("customize-source-label");
  const error = $("customize-error");
  customizeModalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  input.value = defaultCustomStudyName();
  source.textContent = state?.design?.study_profile_title || state?.design?.name || "";
  error.hidden = true;
  error.textContent = "";
  modal.hidden = false;
  document.body.classList.add("modal-open");
  window.setTimeout(() => {
    input.focus();
    input.select();
  }, 0);
}

function closeCustomizeModal() {
  const modal = $("customize-modal");
  if (modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  if (customizeModalReturnFocus && document.contains(customizeModalReturnFocus)) {
    customizeModalReturnFocus.focus();
  }
  customizeModalReturnFocus = null;
}

function showCustomizeError(message) {
  const error = $("customize-error");
  error.textContent = message;
  error.hidden = false;
}

async function submitCustomizeModal() {
  const input = $("customize-study-name");
  const name = input.value.trim();
  if (!name) {
    showCustomizeError("Enter a study name.");
    input.focus();
    return;
  }
  $("customize-submit").disabled = true;
  try {
    await customizeAsNewProject(name);
    closeCustomizeModal();
  } catch (error) {
    showCustomizeError(error.message || String(error));
  } finally {
    $("customize-submit").disabled = false;
  }
}

async function customizeAsNewProject(name) {
  const cleanName = String(name || "").trim();
  if (!cleanName) {
    openCustomizeModal();
    return;
  }
  state = await api("/api/project/customize", {
    method: "POST",
    body: JSON.stringify({ name: cleanName })
  });
  renderAll();
  updateViewer();
  showToast("Custom project created");
  scrollToStep(state.custom_workflow?.current_step || "study");
}

async function startBakeStimulus() {
  if (!ensureEditableProject()) return;
  if (!confirmDownstreamInvalidation("Baking Segment 1 ingredients", "stimulus")) return;
  const recipe = collectBakeRecipe();
  if (!recipe) {
    showToast("Choose a source to bake as a Segment 1 ingredient");
    return;
  }
  const payload = collectPayload();
  payload.bake_recipe = recipe;
  const job = await api("/api/stimulus/bake", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  showToast("Ingredient bake started");
  pollJob(job.job_id);
  await loadState();
}

async function startBakeTrialSequences() {
  if (!ensureEditableProject()) return;
  if (!confirmDownstreamInvalidation("Baking Segment 2 trial sequences", "trials")) return;
  const segment1 = projectSegment("1_core_audio_ingredients");
  const sequence = sequenceVariantEstimate();
  if (segment1.status !== "ready") {
    showToast("Bake or import Segment 1 ingredients first");
    return;
  }
  if (sequence.variantCount <= 0) {
    showToast("Add at least one complete trial sequence row");
    return;
  }
  const payload = collectPayload();
  payload.bake_recipe = { kind: "trial_sequence_batch", label: "2_trial_sequence_designs" };
  const job = await api("/api/stimulus/bake", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  showToast("Trial sequence bake started");
  pollJob(job.job_id);
  await loadState();
}

async function startBakeTrialFiles() {
  if (!ensureEditableProject()) return;
  if (!confirmDownstreamInvalidation("Baking Segment 3 baseline/tactile trial files", "baseline")) return;
  if (projectSegment("2_trial_sequence_designs").status !== "ready") {
    showToast("Bake Segment 2 trial sequences first");
    return;
  }
  const payload = collectPayload();
  payload.bake_recipe = { kind: "audiotactile_trial_batch", label: "3_tactile_and_baseline_trials" };
  const job = await api("/api/stimulus/bake", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  showToast("Baseline/tactile trial bake started");
  pollJob(job.job_id);
  await loadState();
}

function trialPoolBakeRecipe() {
  return {
    kind: "trial_repetition_pool",
    label: "4_trial_repetition_pool",
    default_repetitions: normalizeRepetitionValue(trialPoolRepetitionDraft.defaultRepetitions || 0, 0),
    family_repetitions: { ...trialPoolRepetitionDraft.familyRepetitions },
    folder_repetitions: { ...trialPoolRepetitionDraft.folderRepetitions },
    file_repetition_overrides: { ...trialPoolRepetitionDraft.fileRepetitionOverrides },
    fractional_seed: Number(trialPoolRepetitionDraft.fractionalSeed || state?.design?.protocol?.random_seed || 20250604) || 20250604,
  };
}

async function startBakeTrialPool() {
  if (!ensureEditableProject()) return;
  if (!confirmDownstreamInvalidation("Baking Segment 4 trial pool CSV", "block")) return;
  if (projectSegment("3_tactile_and_baseline_trials").status !== "ready") {
    showToast("Bake Segment 3 trial files first");
    return;
  }
  if (trialPoolCompositionEstimate().totalTrials <= 0) {
    showToast("Set at least one repetition before baking the trial pool");
    return;
  }
  const payload = collectPayload();
  payload.bake_recipe = trialPoolBakeRecipe();
  const job = await api("/api/stimulus/bake", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  showToast("Trial pool CSV bake started");
  pollJob(job.job_id);
  await loadState();
}

async function startBakeBlockCsvs() {
  if (!ensureEditableProject()) return;
  if (!confirmDownstreamInvalidation("Regenerating Segment 5 block CSVs", "schedule")) return;
  if (projectSegment("4_trial_repetition_pool").status !== "ready") {
    showToast("Bake Segment 4 trial pool first");
    return;
  }
  if (projectSegment("5_block_csv_preview").accepted || state.block_csv_preview?.accepted) {
    showToast("Click Edit Blocks before regenerating accepted block CSVs");
    return;
  }
  const blockCount = Math.max(1, Math.round(numberValue("block-count", numberValue("blocks", 1))));
  if ($("blocks")) $("blocks").value = blockCount;
  const blockButton = $("regenerate-block-csvs");
  if (blockButton) blockButton.disabled = true;
  setBlockProgress(0, blockCount, "regenerating block CSVs");
  try {
    const payload = collectPayload();
    payload.bake_recipe = {
      kind: "block_csv_preview",
      label: "5_block_csv_preview",
      block_count: blockCount,
      seed: Date.now() + Math.floor(Math.random() * 1000000),
    };
    const job = await api("/api/stimulus/bake", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    setBlockProgress(job.progress_current || 0, job.progress_total || blockCount, job.progress_label || "queued");
    showToast("Block regeneration started");
    pollJob(job.job_id);
    await loadState();
  } catch (error) {
    setBlockProgress(0, blockCount, error.message || "block CSV bake failed");
    throw error;
  } finally {
    if (blockButton) blockButton.disabled = projectSegment("4_trial_repetition_pool").status !== "ready" || Boolean(projectSegment("5_block_csv_preview").accepted || state.block_csv_preview?.accepted);
  }
}

async function acceptBlockCsvs() {
  if (!ensureEditableProject()) return;
  const segment5 = projectSegment("5_block_csv_preview");
  if (segment5.status !== "ready") {
    showToast("Regenerate blocks first");
    return;
  }
  const acceptButton = $("accept-block-csvs");
  if (acceptButton) acceptButton.disabled = true;
  const accepted = Boolean(segment5.accepted || state.block_csv_preview?.accepted);
  if (accepted && !confirmDownstreamInvalidation("Editing accepted Segment 5 blocks", "schedule")) {
    if (acceptButton) acceptButton.disabled = false;
    return;
  }
  state = await api(accepted ? "/api/block-csv/edit" : "/api/block-csv/accept", { method: "POST" });
  renderAll();
  if (accepted) {
    showToast("Blocks reopened for editing");
    scrollToStep("schedule");
  } else {
    showToast("Blocks accepted; CSVs marked final");
    scrollToStep("run");
  }
}

function scheduleRunSequencePreview() {
  window.clearTimeout(runSequencePreviewTimer);
  renderRun();
  runSequencePreviewTimer = window.setTimeout(() => {
    previewRunSequence().catch(reportError);
  }, 300);
}

async function previewRunSequence() {
  if (!ensureEditableProject()) return;
  state = await api("/api/run-sequence/preview", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
}

async function regenerateRunSequence() {
  if (!ensureEditableProject()) return;
  state = await api("/api/run-sequence/regenerate", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
  showToast("Block sequence regenerated");
}

async function prepareExperiment() {
  const profileRunMode = isProfileReadonlyMode();
  if (!profileRunMode && !ensureEditableProject()) return;
  const prepared = Boolean(state.run_sequence_setup?.prepared || projectSegment("6_experiment_run_setup").status === "ready");
  if (!prepared && !profileRunMode) {
    state = await api("/api/run-sequence/prepare", {
      method: "POST",
      body: JSON.stringify(collectPayload())
    });
  }
  state = await api("/api/run-sequence/open-runner", {
    method: "POST",
    body: JSON.stringify(profileRunMode ? collectProfileRunPayload() : collectPayload())
  });
  renderAll();
  const toastMessage = prepared
    ? "Local runner opened"
    : (profileRunMode ? "Profile run prepared; local runner opened" : "Design saved; local runner opened");
  showToast(toastMessage);
  scrollToStep("run");
}

async function openLocalFolder(path) {
  if (!path) return;
  await api("/api/local/open-folder", {
    method: "POST",
    body: JSON.stringify({ path })
  });
  showToast("Opened local folder");
}

async function pollJob(jobId) {
  if (!jobId || activePolls.has(jobId)) return;
  activePolls.add(jobId);
  for (;;) {
    await delay(900);
    const job = await api(`/api/jobs/${jobId}`);
    await loadState();
    if (job.status === "succeeded" || job.status === "failed") {
      activePolls.delete(jobId);
      if (job.status === "succeeded" && (job.kind === "stimulus_bake" || job.kind === "block_csv_preview")) {
        if (!["audiotactile_trial_batch", "trial_sequence_batch", "trial_repetition_pool"].includes(job.result?.source_kind)) {
          pendingBakeRecipe = null;
          if (job.kind === "stimulus_bake") $("generated-noise-select").value = "";
        }
        renderBakePanel();
        renderBaselineTactileSummary();
        renderBlockCsvPreview();
        renderProtocolSummary();
      }
      showToast(`${humanize(job.kind)} ${job.status}`);
      break;
    }
  }
}

function updateViewer() {
  if (!state || !viewerReady) return;
  const frame = $("trajectory-frame");
  const payload = trajectoryPayloadFromControls();
  syncPreviewModeControls(payload.preview_mode);
  const updateTrajectory = frame.contentWindow?.updateTrajectory;
  if (typeof updateTrajectory !== "function") {
    window.setTimeout(updateViewer, 150);
    return;
  }
  updateTrajectory(payload);
}

function setPreviewMode(mode) {
  const nextMode = mode === "3d" ? "3d" : "2d";
  $("preview-mode").value = nextMode;
  syncPreviewModeControls(nextMode);
  updateViewer();
}

function callTrajectoryViewer(method, ...args) {
  const frame = $("trajectory-frame");
  const fn = frame.contentWindow?.[method];
  if (typeof fn === "function") fn(...args);
}

function currentTrajectoryControls() {
  return {
    start_distance_cm: clampNumber(numberValue("start-distance", 110), 1, 1000, 110),
    end_distance_cm: clampNumber(numberValue("end-distance", 10), 1, 1000, 10),
    start_rotation_deg: normalizeRotationDeg(numberValue("start-rotation", 0)),
    end_rotation_deg: normalizeRotationDeg(numberValue("end-rotation", 0)),
    movement_duration_s: clampNumber(numberValue("movement-duration", 3), 0.1, 30, 3),
    start_hold_s: clampNumber(numberValue("start-hold", 0.5), 0, 30, 0.5),
    end_hold_s: clampNumber(numberValue("end-hold", 0.5), 0, 30, 0.5)
  };
}

function trajectoryPayloadFromControls() {
  const controls = currentTrajectoryControls();
  const start = pointFromDistanceRotation(controls.start_distance_cm, controls.start_rotation_deg);
  const end = pointFromDistanceRotation(controls.end_distance_cm, controls.end_rotation_deg);
  const pathLength = distance3d(start, end);
  const sourceTrajectories = sourceTrajectoriesFromDom();
  const sourceRadius = maxSourceTrajectoryRadius(sourceTrajectories);
  const radius = Math.max(0.1, controls.start_distance_cm / 100, controls.end_distance_cm / 100, sourceRadius);
  return {
    ...clone(state.viewer_payload || {}),
    preview_mode: $("preview-mode").value || "2d",
    radius_m: radius,
    path_length_m: pathLength,
    movement_duration_s: controls.movement_duration_s,
    start,
    end,
    controls,
    source_trajectories: sourceTrajectories
  };
}

function sourceTrajectoriesFromDom() {
  const rows = [];
  for (const card of $("noise-list").querySelectorAll(".noise-source-card")) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const label = field("label")?.value.trim() || "Generated noise";
    const toneType = field("noise_type")?.value || "pink";
    const snapshot = readJsonField(field("trajectory_snapshot"));
    const row = sourceTrajectoryRow({
      label,
      sourceKind: "generated_noise",
      toneType,
      localPath: field("prebaked_path")?.value || "",
      snapshot
    });
    if (row) rows.push(row);
  }
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const role = field("audio_role")?.value || "preserve";
    if (role === "prestimulus") continue;
    const label = field("label")?.value.trim() || audioRoleTitle(role);
    const toneType = field("tone_type")?.value || "custom_audio";
    const row = sourceTrajectoryRow({
      label,
      sourceKind: "imported_audio",
      toneType,
      localPath: field("path")?.value || "",
      snapshot: readJsonField(field("trajectory_snapshot"))
    });
    if (row) rows.push(row);
  }
  return rows.length ? rows : clone(state.viewer_payload?.source_trajectories || []);
}

function sourceTrajectoryRow({ label, sourceKind, toneType, localPath, snapshot }) {
  if (!snapshot || !snapshot.start || !snapshot.end) return null;
  return {
    label,
    source_kind: sourceKind,
    tone_type: toneType,
    color_hex: sourceColor(toneType),
    local_path: localPath,
    trajectory_snapshot: snapshot,
    start: snapshot.start,
    end: snapshot.end,
    path_length_m: snapshot.path_length_m,
    movement_duration_s: snapshot.movement_duration_s
  };
}

function maxSourceTrajectoryRadius(rows = []) {
  let radius = 0;
  for (const row of rows) {
    for (const point of [row.start, row.end]) {
      if (!point) continue;
      const value = Math.sqrt(Number(point.x_m || 0) ** 2 + Number(point.y_m || 0) ** 2 + Number(point.z_m || 0) ** 2);
      if (Number.isFinite(value)) radius = Math.max(radius, value);
    }
  }
  return radius;
}

function pointFromDistanceRotation(distanceCm, rotationDeg) {
  const radiusM = distanceCm / 100;
  const radians = (normalizeSignedRotationDeg(rotationDeg) * Math.PI) / 180;
  return {
    x_m: radiusM * Math.sin(radians),
    y_m: radiusM * Math.cos(radians),
    z_m: 0
  };
}

function distance3d(start, end) {
  const dx = Number(start.x_m || 0) - Number(end.x_m || 0);
  const dy = Number(start.y_m || 0) - Number(end.y_m || 0);
  const dz = Number(start.z_m || 0) - Number(end.z_m || 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function normalizeRotationDeg(value) {
  const rotation = Number(value);
  if (!Number.isFinite(rotation)) return 0;
  return ((rotation % 360) + 360) % 360;
}

function normalizeSignedRotationDeg(value) {
  return ((normalizeRotationDeg(value) + 180) % 360) - 180;
}

function applyTrajectoryControlUpdate(controls) {
  const fields = {
    start_distance_cm: "start-distance",
    end_distance_cm: "end-distance",
    start_rotation_deg: "start-rotation",
    end_rotation_deg: "end-rotation",
    movement_duration_s: "movement-duration",
    start_hold_s: "start-hold",
    end_hold_s: "end-hold"
  };
  for (const [key, id] of Object.entries(fields)) {
    if (controls[key] === undefined) continue;
    $(id).value = formatTrajectoryValue(key, controls[key]);
  }
  state.trajectory_controls = { ...(state.trajectory_controls || {}), ...currentTrajectoryControls() };
  updateViewer();
}

function formatTrajectoryValue(key, value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  const decimals = key.endsWith("_deg") || key.endsWith("_cm") ? 1 : 2;
  return String(Number(numeric.toFixed(decimals)));
}

function syncPreviewModeControls(mode) {
  const current = mode === "3d" ? "3d" : "2d";
  for (const button of document.querySelectorAll("[data-preview-mode]")) {
    button.classList.toggle("active", button.dataset.previewMode === current);
    button.setAttribute("aria-pressed", String(button.dataset.previewMode === current));
  }
}

function getWorkflowStep(stepId) {
  return (state.custom_workflow?.steps || []).find((step) => step.id === stepId);
}

function ensureWorkflowAction(key) {
  const workflow = state.custom_workflow || {};
  if (!workflow.is_custom || workflow[key]) return true;
  const missing = workflow.missing || [];
  showToast(missing.length ? missing.join(" ") : "Complete the custom design steps first.");
  scrollToStep(workflow.current_step || "study");
  return false;
}

function stepLabel(stepId) {
  return (getWorkflowStep(stepId)?.label || humanize(stepId)).toLowerCase();
}

function scrollToStep(stepId) {
  const target = $(STEP_TARGETS[stepId] || stepId);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function updateActiveNav() {
  if (activePage !== "toolkit") {
    for (const link of document.querySelectorAll("[data-step-link]")) {
      link.classList.remove("active");
    }
    const pageLinks = [...document.querySelectorAll(`[data-page-section-page="${cssEscape(activePage)}"]`)];
    let activeSection = pageLinks[0]?.dataset.pageSectionLink || "";
    const viewportTop = 96;
    for (const link of pageLinks) {
      const target = $(link.dataset.pageSectionLink);
      if (!target) continue;
      if (target.getBoundingClientRect().top <= viewportTop) {
        activeSection = link.dataset.pageSectionLink;
      }
    }
    const hashSection = String(topLevelHash() || "").replace(/^#/, "");
    if (pageLinks.some((link) => link.dataset.pageSectionLink === hashSection)) {
      activeSection = hashSection;
    }
    for (const link of document.querySelectorAll("[data-page-section-link]")) {
      link.classList.toggle(
        "active",
        link.dataset.pageSectionPage === activePage && link.dataset.pageSectionLink === activeSection
      );
    }
    return;
  }
  for (const link of document.querySelectorAll("[data-page-section-link]")) {
    link.classList.remove("active");
  }
  let active = "study";
  const viewportTop = 96;
  for (const stepId of WORKFLOW_STEPS) {
    const target = $(STEP_TARGETS[stepId]);
    if (!target) continue;
    if (target.getBoundingClientRect().top <= viewportTop) {
      active = stepId;
    }
  }
  for (const link of document.querySelectorAll("[data-step-link]")) {
    link.classList.toggle("active", link.dataset.stepLink === active);
  }
}

function scheduleActiveNavUpdate() {
  if (activeNavFrame) return;
  activeNavFrame = window.requestAnimationFrame(() => {
    activeNavFrame = 0;
    updateActiveNav();
  });
}

function loadResizableLayoutSettings() {
  applySplitSetting("sideWidth", Number(localStorage.getItem(splitStorageKey("sideWidth"))) || SPLIT_DEFAULTS.sideWidth, false);
  applySplitSetting("ordersWidth", Number(localStorage.getItem(splitStorageKey("ordersWidth"))) || SPLIT_DEFAULTS.ordersWidth, false);
  initializeResizablePanels();
}

function initializeResizablePanels() {
  for (const panel of document.querySelectorAll("[data-resizable-panel]")) {
    const panelId = panel.dataset.panelId || panel.id;
    const storedHeight = Number(localStorage.getItem(panelStorageKey(panelId)));
    if (Number.isFinite(storedHeight) && storedHeight > 0) {
      setPanelHeight(panel, storedHeight, false);
    }
    if (panel.querySelector(":scope > .panel-resize-handle")) continue;
    const handle = document.createElement("div");
    handle.className = "panel-resize-handle";
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "horizontal");
    handle.setAttribute("aria-label", `Resize ${panelId.replaceAll("-", " ")} panel`);
    handle.tabIndex = 0;
    handle.addEventListener("pointerdown", (event) => startPanelResize(event, panel, handle));
    handle.addEventListener("keydown", (event) => resizePanelFromKeyboard(event, panel));
    panel.appendChild(handle);
  }
}

function setPanelHeight(panel, value, persist = true) {
  const panelId = panel.dataset.panelId || panel.id;
  const height = snapNumber(clampNumber(Number(value), PANEL_HEIGHT_MIN, PANEL_HEIGHT_MAX, PANEL_HEIGHT_MIN));
  panel.style.setProperty("--panel-user-height", `${height}px`);
  panel.classList.add("user-sized");
  if (persist) {
    localStorage.setItem(panelStorageKey(panelId), String(height));
  }
  if (panel.dataset.panelId === "trajectory-preview") {
    window.requestAnimationFrame(updateViewer);
  }
}

function startPanelResize(event, panel, handle) {
  if (event.button !== 0) return;
  event.preventDefault();
  const startY = event.clientY;
  const startHeight = panel.getBoundingClientRect().height;
  document.body.classList.add("resizing-panel");
  handle.classList.add("active");

  const onMove = (moveEvent) => {
    setPanelHeight(panel, startHeight + moveEvent.clientY - startY, false);
  };
  const onUp = (upEvent) => {
    setPanelHeight(panel, startHeight + upEvent.clientY - startY, true);
    document.body.classList.remove("resizing-panel");
    handle.classList.remove("active");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function resizePanelFromKeyboard(event, panel) {
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  const direction = event.key === "ArrowDown" ? 1 : -1;
  const currentHeight = panel.getBoundingClientRect().height;
  setPanelHeight(panel, currentHeight + direction * PANEL_RESIZE_SNAP_PX, true);
}

function wireSplitters() {
  for (const gutter of document.querySelectorAll("[data-resize-gutter]")) {
    gutter.addEventListener("pointerdown", (event) => startSplitterResize(event, gutter));
    gutter.addEventListener("keydown", (event) => resizeSplitterFromKeyboard(event, gutter));
  }
}

function startSplitterResize(event, gutter) {
  if (event.button !== 0) return;
  event.preventDefault();
  const key = splitKeyForGutter(gutter);
  const container = gutter.closest(".grid, .table-grid, .stimulus-grid, .run-grid");
  if (!container) return;
  const rect = container.getBoundingClientRect();
  document.body.classList.add("resizing-layout");
  gutter.classList.add("active");

  const onMove = (moveEvent) => {
    applySplitSetting(key, rect.right - moveEvent.clientX, false, rect);
  };
  const onUp = (upEvent) => {
    applySplitSetting(key, rect.right - upEvent.clientX, true, rect);
    document.body.classList.remove("resizing-layout");
    gutter.classList.remove("active");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function resizeSplitterFromKeyboard(event, gutter) {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const key = splitKeyForGutter(gutter);
  const direction = event.key === "ArrowLeft" ? 1 : -1;
  const cssVar = key === "sideWidth" ? "--side-column-width" : "--orders-column-width";
  const current = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(cssVar));
  const container = gutter.closest(".grid, .table-grid, .stimulus-grid, .run-grid");
  if (!container) return;
  applySplitSetting(key, current + direction * PANEL_RESIZE_SNAP_PX, true, container.getBoundingClientRect());
}

function applySplitSetting(key, value, persist = true, containerRect = null) {
  const limits = splitLimitsFor(key, containerRect);
  const width = snapNumber(clampNumber(Number(value), limits.min, limits.max, SPLIT_DEFAULTS[key]));
  const cssVar = key === "sideWidth" ? "--side-column-width" : "--orders-column-width";
  document.documentElement.style.setProperty(cssVar, `${width}px`);
  if (persist) {
    localStorage.setItem(splitStorageKey(key), String(width));
  }
  if (key === "sideWidth") {
    window.requestAnimationFrame(updateViewer);
  }
}

function splitLimitsFor(key, containerRect = null) {
  const limits = SPLIT_LIMITS[key];
  const width = containerRect ? containerRect.width : window.innerWidth - 260;
  const reserved = key === "sideWidth" ? 430 : 320;
  return {
    min: limits.min,
    max: Math.max(limits.min, Math.min(limits.max, width - reserved))
  };
}

function splitKeyForGutter(gutter) {
  return gutter.dataset.resizeGutter === "tables" ? "ordersWidth" : "sideWidth";
}

function splitStorageKey(key) {
  return `ppsDashboard.split.${key}`;
}

function panelStorageKey(panelId) {
  return `ppsDashboard.panelHeight.${panelId}`;
}

function snapNumber(value, step = PANEL_RESIZE_SNAP_PX) {
  return Math.round(value / step) * step;
}

function clampNumber(value, min, max, fallback) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function stageGeneratedNoise(noiseType = "pink") {
  const type = PROCEDURAL_NOISE_TYPES.some((item) => item.value === noiseType) ? noiseType : "pink";
  const label = `${noiseTypeLabel(type)} noise`;
  pendingBakeRecipe = {
    kind: "generated_noise",
    noise_type: type,
    label,
    gain: Number($("bake-gain")?.value || 1)
  };
  $("bake-label").value = label;
  renderBakePanel();
  showToast(`${noiseTypeLabel(type)} noise staged`);
}

function stageImportedAudioForBake(audio, renderMode) {
  const mode = renderMode === "spatialize" ? "spatialize" : "preserve";
  pendingBakeRecipe = {
    kind: "imported_audio",
    render_mode: mode,
    label: audio.label || audioRoleTitle(mode),
    audio,
    gain: Number(audio.gain || 1)
  };
  $("bake-label").value = pendingBakeRecipe.label;
  renderBakePanel();
}

function collectBakeRecipe() {
  if (!pendingBakeRecipe) return null;
  const recipe = clone(pendingBakeRecipe);
  recipe.label = $("bake-label").value.trim() || recipe.label || "Baked stimulus";
  recipe.gain = Math.max(0.01, Number($("bake-gain").value || recipe.gain || 1));
  if (recipe.audio) {
    recipe.audio = {
      ...recipe.audio,
      label: recipe.label,
      gain: recipe.gain
    };
  }
  return recipe;
}

function addNoiseRow(noiseType = "pink") {
  const type = PROCEDURAL_NOISE_TYPES.some((item) => item.value === noiseType) ? noiseType : "pink";
  state.design.noises = state.design.noises || [];
  const label = noiseTypeLabel(type);
  state.design.noises.push({
    label: `${label} noise`,
    noise_type: type,
    azimuth_deg: 0,
    elevation_deg: 0,
    gain: 1
  });
  renderNoiseTable();
  refreshAssemblyTargetOptions();
  syncFilmstripSourceOptions();
  renderSourceCounts();
}

function noiseTypeLabel(noiseType) {
  return PROCEDURAL_NOISE_TYPES.find((item) => item.value === noiseType)?.label || "Generated";
}

function audioRoleTitle(role) {
  if (role === "spatialize") return "Custom looming tone";
  if (role === "prestimulus") return "Custom clip";
  return "Custom audio clip";
}

function openAudioPicker(renderMode) {
  pendingInstructionSlot = "";
  pendingAudioImportMode = ["spatialize", "prestimulus"].includes(renderMode) ? renderMode : "preserve";
  $("audio-file-input").click();
}

function openInstructionAudioPicker(slot) {
  pendingInstructionSlot = slot;
  pendingAudioImportMode = "instruction";
  $("audio-file-input").click();
}

async function importAudioFromPicker() {
  const input = $("audio-file-input");
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  const contentBase64 = await fileToBase64(file);
  if (pendingInstructionSlot) {
    const current = collectRunInstructionProfile().slots.find((slot) => slot.slot === pendingInstructionSlot) || {};
    const importedState = await api("/api/run-instructions/import", {
      method: "POST",
      body: JSON.stringify({
        slot: pendingInstructionSlot,
        filename: file.name,
        content_base64: contentBase64,
        label: current.label || file.name.replace(/\.[^.]+$/, "")
      })
    });
    state = importedState;
    pendingInstructionSlot = "";
    renderAll();
    showToast("Instruction audio clip imported locally");
    return;
  }
  const imported = await api("/api/audio/import", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      content_base64: contentBase64,
      use: pendingAudioImportMode === "prestimulus" ? "prestimulus" : "looming",
      render_mode: pendingAudioImportMode === "spatialize" ? "spatialize" : "preserve",
      motion_mode: pendingAudioImportMode === "preserve" || pendingAudioImportMode === "prestimulus" ? "stationary" : "looming",
      placement: "before",
      target_source_label: "",
      phase: "",
      gap_s: 0
    })
  });
  if (pendingAudioImportMode === "prestimulus") {
    state.design.prestimulus_files = state.design.prestimulus_files || [];
    state.design.prestimulus_files.push({ ...imported.audio, placement: "before", target_source_label: "", phase: "", gap_s: 0 });
    renderAudioTable();
    refreshAssemblyTargetOptions();
    syncFilmstripSourceOptions();
    renderSourceCounts();
    showToast("Custom clip imported locally");
  } else if (pendingAudioImportMode === "preserve") {
    state.design.custom_looming_files = state.design.custom_looming_files || [];
    state.design.custom_looming_files.push({
      ...imported.audio,
      render_mode: "preserve",
      motion_mode: "stationary",
      tone_type: imported.audio.tone_type || "custom_audio",
      trajectory_snapshot: {}
    });
    pendingBakeRecipe = null;
    renderBakePanel();
    renderAudioTable();
    refreshAssemblyTargetOptions();
    syncFilmstripSourceOptions();
    renderSourceCounts();
    updateViewer();
    showToast("Custom audio clip imported locally");
  } else {
    stageImportedAudioForBake(imported.audio, pendingAudioImportMode);
    showToast("Audio staged for baking");
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",").pop() : result);
    });
    reader.addEventListener("error", () => reject(reader.error || new Error("Could not read audio file")));
    reader.readAsDataURL(file);
  });
}

function removeSourceCard(button) {
  const card = button.closest(".source-card");
  if (card) card.remove();
  refreshAssemblyTargetOptions();
  syncFilmstripSourceOptions();
  renderSourceCounts();
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function humanize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}

function doiUrl(value) {
  const doi = String(value || "").trim();
  if (/^https?:\/\//i.test(doi)) {
    return doi;
  }
  return `https://doi.org/${doi.replace(/^doi:\s*/i, "")}`;
}

function enforceExternalLinkTargets(root = document) {
  for (const link of root.querySelectorAll("a[href]")) {
    let url;
    try {
      url = new URL(link.getAttribute("href"), window.location.href);
    } catch (_err) {
      continue;
    }
    if (!/^https?:$/i.test(url.protocol) || url.origin === window.location.origin) continue;
    link.target = "_blank";
    const relTokens = new Set((link.getAttribute("rel") || "").split(/\s+/).filter(Boolean));
    relTokens.add("noopener");
    relTokens.add("noreferrer");
    link.setAttribute("rel", Array.from(relTokens).join(" "));
  }
}

function renderHardwarePixelArt() {
  const store = window.HARDWARE_PIXEL_ART || {};
  for (const canvas of document.querySelectorAll("canvas[data-hardware-pixel]")) {
    const key = canvas.dataset.hardwarePixel || "";
    const art = store[key];
    if (!art?.rgb || !art.width || !art.height || canvas.dataset.pixelRendered === "true") continue;
    const width = Number(art.width);
    const height = Number(art.height);
    const binary = window.atob(art.rgb);
    const rgba = new Uint8ClampedArray(width * height * 4);
    for (let source = 0, target = 0; source < binary.length; source += 3, target += 4) {
      rgba[target] = binary.charCodeAt(source);
      rgba[target + 1] = binary.charCodeAt(source + 1);
      rgba[target + 2] = binary.charCodeAt(source + 2);
      rgba[target + 3] = 255;
    }
    canvas.width = width;
    canvas.height = height;
    canvas.dataset.pixelRendered = "true";
    const context = canvas.getContext("2d");
    context.imageSmoothingEnabled = false;
    context.putImageData(new ImageData(rgba, width, height), 0, 0);
  }
}

function wireEvents() {
  $("refresh-state").addEventListener("click", () => loadState().catch(reportError));
  $("apply-design").addEventListener("click", () => applyDesign().catch(reportError));
  $("connect-backend").addEventListener("click", () => {
    saveApiBase($("backend-url").value);
    loadState().catch(reportError);
  });
  for (const button of document.querySelectorAll("[data-page-tab]")) {
    button.addEventListener("click", () => setActivePage(button.dataset.pageTab, { updateHash: true, scrollTop: true }));
  }
  for (const link of document.querySelectorAll("[data-page-section-link]")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const targetId = link.dataset.pageSectionLink;
      const page = link.dataset.pageSectionPage;
      setActivePage(page, { updateHash: false, scrollTop: false });
      const target = $(targetId);
      if (target) {
        replaceRouteForPage(page, targetId);
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        setActivePageSection(targetId);
        window.setTimeout(() => setActivePageSection(targetId), 350);
      }
    });
  }
  window.addEventListener("hashchange", () => {
    const nextPage = pageFromLocation();
    if (nextPage) {
      setActivePage(nextPage, { scrollTop: false });
      scrollToHashTarget();
    }
  });
  window.addEventListener("scroll", scheduleActiveNavUpdate, { passive: true });
  for (const button of document.querySelectorAll("[data-segment-info]")) {
    button.addEventListener("click", () => openSegmentInfoModal(button.dataset.segmentInfo, button));
  }
  $("segment-info-modal-close")?.addEventListener("click", closeSegmentInfoModal);
  $("segment-info-modal")?.addEventListener("click", (event) => {
    if (event.target === $("segment-info-modal")) closeSegmentInfoModal();
  });
  $("edit-profile-rail")?.addEventListener("click", openCustomizeModal);
  $("customize-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCustomizeModal().catch(reportError);
  });
  $("customize-cancel")?.addEventListener("click", closeCustomizeModal);
  $("customize-modal-close")?.addEventListener("click", closeCustomizeModal);
  $("customize-modal")?.addEventListener("click", (event) => {
    if (event.target === $("customize-modal")) closeCustomizeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!$("segment-info-modal")?.hidden) {
      closeSegmentInfoModal();
    } else if (!$("customize-modal")?.hidden) {
      closeCustomizeModal();
    }
  });
  $("backend-url").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      saveApiBase($("backend-url").value);
      loadState().catch(reportError);
    }
  });
  $("template-select").addEventListener("change", () => {
    renderProfileSummary();
    loadTemplate().catch(reportError);
  });
  $("existing-custom-project")?.addEventListener("change", () => {
    const button = $("load-custom-project");
    if (button) button.disabled = !$("existing-custom-project").value;
  });
  $("load-custom-project")?.addEventListener("click", () => loadCustomProject().catch(reportError));
  $("apply-profile-project")?.addEventListener("click", () => continueWorkflowStep("study").catch(reportError));
  $("bake-stimulus").addEventListener("click", () => startBakeStimulus().catch(reportError));
  $("bake-trial-sequences")?.addEventListener("click", () => startBakeTrialSequences().catch(reportError));
  $("bake-trial-files")?.addEventListener("click", () => startBakeTrialFiles().catch(reportError));
  $("bake-trial-pool")?.addEventListener("click", () => startBakeTrialPool().catch(reportError));
  $("regenerate-block-csvs")?.addEventListener("click", () => startBakeBlockCsvs().catch(reportError));
  $("accept-block-csvs")?.addEventListener("click", () => acceptBlockCsvs().catch(reportError));
  $("open-profile-folder")?.addEventListener("click", () => {
    const path = $("open-profile-folder")?.dataset.folderPath || projectSegment("0_profile").folder_path || "";
    openLocalFolder(path).catch(reportError);
  });
  $("open-ingredient-folder")?.addEventListener("click", () => {
    const path = $("open-ingredient-folder")?.dataset.folderPath || projectSegment("1_core_audio_ingredients").folder_path || "";
    openLocalFolder(path).catch(reportError);
  });
  $("open-trial-sequence-folder")?.addEventListener("click", () => {
    const path = $("open-trial-sequence-folder")?.dataset.folderPath || projectSegment("2_trial_sequence_designs").folder_path || "";
    openLocalFolder(path).catch(reportError);
  });
  $("open-trial-file-folder")?.addEventListener("click", () => {
    const path = $("open-trial-file-folder")?.dataset.folderPath || state.trial_file_bake?.root || "";
    openLocalFolder(path).catch(reportError);
  });
  $("open-trial-pool-folder")?.addEventListener("click", () => {
    const path = $("open-trial-pool-folder")?.dataset.folderPath || state.trial_pool_bake?.root || "";
    openLocalFolder(path).catch(reportError);
  });
  $("regenerate-run-sequence")?.addEventListener("click", () => regenerateRunSequence().catch(reportError));
  $("prepare-experiment")?.addEventListener("click", () => prepareExperiment().catch(reportError));
  $("generated-noise-select").addEventListener("change", () => {
    const selectedNoise = $("generated-noise-select").value;
    if (!selectedNoise) return;
    stageGeneratedNoise(selectedNoise);
  });
  $("bake-label").addEventListener("input", () => {
    if (pendingBakeRecipe) pendingBakeRecipe.label = $("bake-label").value.trim();
  });
  $("bake-gain").addEventListener("input", () => {
    if (pendingBakeRecipe) pendingBakeRecipe.gain = Math.max(0.01, Number($("bake-gain").value || 1));
  });
  $("import-audio-spatialize").addEventListener("click", () => openAudioPicker("spatialize"));
  $("import-audio-preserve").addEventListener("click", () => openAudioPicker("preserve"));
  $("import-audio-prestimulus")?.addEventListener("click", () => openAudioPicker("prestimulus"));
  $("audio-file-input").addEventListener("change", () => importAudioFromPicker().catch(reportError));
  $("soa-values").addEventListener("input", updateFilmstripCounts);
  $("block-soa-values").addEventListener("input", () => {
    syncCompositionSoaInputs($("block-soa-values"));
    updateFilmstripCounts();
  });
  $("repetitions").addEventListener("input", () => {
    trialPoolRepetitionDraft.defaultRepetitions = normalizeRepetitionValue(numberValue("repetitions", 0), 0);
    updateFilmstripCounts();
  });
  $("apply-trial-pool-repetitions")?.addEventListener("click", () => {
    const next = normalizeRepetitionValue(numberValue("repetitions", 0), 0);
    trialPoolRepetitionDraft.defaultRepetitions = next;
    trialPoolRepetitionDraft.familyRepetitions = {};
    trialPoolRepetitionDraft.folderRepetitions = {};
    trialPoolRepetitionDraft.fileRepetitionOverrides = {};
    for (const group of trialPoolFolderGroups()) {
      trialPoolRepetitionDraft.folderRepetitions[group.folderKey] = next;
    }
    updateFilmstripCounts();
  });
  $("blocks").addEventListener("input", updateFilmstripCounts);
  $("block-count")?.addEventListener("input", () => {
    const blockCount = Math.max(1, Math.round(numberValue("block-count", 1)));
    if ($("blocks")) $("blocks").value = blockCount;
    renderBlockCsvPreview();
  });
  $("participants").addEventListener("input", scheduleRunSequencePreview);
  for (const input of document.querySelectorAll('input[name="experiment-structure"]')) {
    input.addEventListener("change", scheduleRunSequencePreview);
  }
  $("run-instruction-slots")?.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-instruction-import]");
    if (!button) return;
    openInstructionAudioPicker(button.dataset.instructionImport || "");
  });
  $("run-instruction-slots")?.addEventListener("input", scheduleRunSequencePreview);
  $("run-instruction-slots")?.addEventListener("change", scheduleRunSequencePreview);
  $("baseline-enabled").addEventListener("change", () => {
    const previous = $("baseline-strategy").value;
    const nextStrategy = $("baseline-enabled").checked
      ? (previous && previous !== "none" ? previous : "tactile_only")
      : "";
    setBaselineStrategy(nextStrategy);
    if (nextStrategy === "none") applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
  $("baseline-strategy").addEventListener("change", () => {
    const nextStrategy = $("baseline-strategy").value || "";
    setBaselineStrategy(nextStrategy);
    if (nextStrategy === "none") applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
  for (const input of baselineOptionInputs()) {
    input.addEventListener("change", () => {
      const nextStrategy = strategyFromBaselineCheckboxes(input);
      setBaselineStrategy(nextStrategy);
      if (!baselineStrategyIsActive(nextStrategy)) applyBaselineDefaultToTrialRows();
      updateFilmstripCounts();
    });
  }
  $("baseline-percent").addEventListener("input", () => {
    enforceGlobalPercentBounds("baseline-percent");
    applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
  $("catch-percent").addEventListener("input", () => {
    enforceGlobalPercentBounds("catch-percent");
    applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
  $("include-catch-trials")?.addEventListener("change", () => {
    updateBaselineDecision();
    updateFilmstripCounts();
  });
  $("baseline-soa-values").addEventListener("input", () => {
    updateBaselineDecision();
    updateFilmstripCounts();
  });
  $("baseline-custom-audio-tactile")?.addEventListener("change", () => {
    updateBaselineDecision();
    updateFilmstripCounts();
  });
  $("row-mix-overrides")?.addEventListener("input", (event) => {
    const input = event.target.closest?.("[data-row-mix-index][data-row-mix-field]");
    if (!input) return;
    const row = [...$("filmstrip-list").querySelectorAll(".filmstrip-row")][Number(input.dataset.rowMixIndex || 0)];
    const field = row?.querySelector(`[data-strip-field="${input.dataset.rowMixField}"]`);
    if (!field) return;
    const next = Math.max(0, Math.min(100, Number(input.value || 0)));
    input.value = String(next);
    field.value = String(next);
    field.dataset.rowMixOverride = "true";
    updateFilmstripCounts();
    const counts = rowCompositionCounts(row);
    const totalCell = input.closest("tr")?.children?.[4];
    if (totalCell) totalCell.textContent = String(counts.totalPerBlock);
  });
  $("trial-pool-folder-list")?.addEventListener("input", (event) => {
    const folderInput = event.target.closest?.("[data-trial-pool-folder]");
    const fileInput = event.target.closest?.("[data-trial-pool-file]");
    if (folderInput) {
      const key = folderInput.dataset.trialPoolFolder || "";
      const value = normalizeRepetitionValue(folderInput.value || 0, 0);
      folderInput.value = formatRepetitionValue(value);
      if (key) trialPoolRepetitionDraft.folderRepetitions[key] = value;
      updateFilmstripCounts();
      return;
    }
    if (fileInput) {
      const key = fileInput.dataset.trialPoolFile || "";
      const value = normalizeRepetitionValue(fileInput.value || 0, 0);
      fileInput.value = formatRepetitionValue(value);
      if (key) trialPoolRepetitionDraft.fileRepetitionOverrides[key] = value;
      updateFilmstripCounts();
    }
  });
  $("reset-camera").addEventListener("click", () => {
    callTrajectoryViewer("resetTrajectoryCamera");
  });
  $("fit-radius-camera").addEventListener("click", () => callTrajectoryViewer("fitTrajectoryRadius"));
  $("zoom-in-camera").addEventListener("click", () => callTrajectoryViewer("zoomTrajectoryCamera", "in"));
  $("zoom-out-camera").addEventListener("click", () => callTrajectoryViewer("zoomTrajectoryCamera", "out"));
  $("preview-mode").addEventListener("change", () => setPreviewMode($("preview-mode").value));
  for (const id of TRAJECTORY_FIELD_IDS) {
    $(id).addEventListener("input", updateViewer);
  }
  wireSplitters();
  for (const button of document.querySelectorAll("[data-preview-mode]")) {
    button.addEventListener("click", () => setPreviewMode(button.dataset.previewMode));
  }
  for (const button of document.querySelectorAll("[data-continue-step]")) {
    button.addEventListener("click", () => continueWorkflowStep(button.dataset.continueStep).catch(reportError));
  }
  for (const link of document.querySelectorAll("[data-step-link]")) {
    link.addEventListener("click", (event) => {
      const stepId = link.dataset.stepLink;
      if (link.classList.contains("locked")) {
        event.preventDefault();
        showToast("Complete the current custom step first.");
        scrollToStep(state.custom_workflow?.current_step || "study");
      } else {
        event.preventDefault();
        setActivePage("toolkit", { updateHash: true });
        scrollToStep(stepId);
      }
    });
  }
  window.addEventListener("scroll", updateActiveNav, { passive: true });
  window.addEventListener("message", (event) => {
    const frame = $("trajectory-frame");
    if (event.source !== frame.contentWindow) return;
    const data = event.data || {};
    if (data.type !== "pps-trajectory-control-change") return;
    applyTrajectoryControlUpdate(data.controls || {});
  });
  $("trajectory-frame").addEventListener("load", () => {
    viewerReady = true;
    updateViewer();
  });
  document.addEventListener("click", (event) => {
    const previewButton = event.target.closest?.("[data-preview-strip]");
    if (previewButton) {
      previewFilmstripRow(previewButton).catch(reportError);
      return;
    }
    const sourcePreviewButton = event.target.closest?.("[data-preview-source-label]");
    if (sourcePreviewButton) {
      previewSourceLabel(sourcePreviewButton).catch(reportError);
      return;
    }
    if (event.target.matches("[data-open-folder]")) {
      openLocalFolder(event.target.dataset.openFolder).catch(reportError);
      return;
    }
    if (event.target.matches("[data-remove-noise], [data-remove-audio]")) {
      removeSourceCard(event.target);
    }
    if (event.target.matches("[data-remove-strip]")) {
      removeFilmstripRow(event.target);
    }
    if (event.target.matches("[data-remove-strip-element]")) {
      removeFilmstripElement(event.target);
    }
    if (event.target.matches("[data-add-strip-element]")) {
      addFilmstripElement(event.target, event.target.dataset.addStripElement);
    }
    if (event.target.matches("[data-add-strip-row]")) {
      addFilmstripRow("fixed_audio", event.target.dataset.insertRowAfter);
    }
    if (event.target.matches("[data-add-box-label]")) {
      addBoxLabel(event.target);
    }
    if (event.target.matches("[data-remove-box-label]")) {
      removeBoxLabel(event.target);
    }
    if (event.target.matches("[data-strip-move]")) {
      moveFilmstripRow(event.target, event.target.dataset.stripMove);
    }
  });
  document.addEventListener("input", (event) => {
    const card = event.target.closest?.(".source-card");
    if (card && event.target.matches('[data-field="label"]')) {
      refreshAssemblyTargetOptions();
      syncFilmstripSourceOptions();
      updateViewer();
    }
    if (event.target.closest?.(".filmstrip-row")) {
      state.design.protocol.trial_strips = collectTrialStrips();
      updateFilmstripCounts();
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.matches('[data-field="audio_role"]')) {
      const card = event.target.closest(".audio-source-card");
      const title = card?.querySelector(".source-card-heading strong");
      if (card) card.dataset.audioRole = event.target.value;
      if (title) title.textContent = audioRoleTitle(event.target.value);
      const motionField = card?.querySelector('[data-field="motion_mode"]');
      if (motionField) {
        motionField.value = event.target.value === "preserve" || event.target.value === "prestimulus" ? "stationary" : "looming";
      }
      applySourceCardColor(card, event.target.value === "prestimulus" ? "prestimulus" : card?.querySelector('[data-field="tone_type"]')?.value || "custom_audio");
      refreshAssemblyTargetOptions();
      syncFilmstripSourceOptions();
      renderSourceCounts();
      updateViewer();
    }
    if (event.target.matches('.audio-source-card [data-field="tone_type"]')) {
      const card = event.target.closest(".audio-source-card");
      applySourceCardColor(card, event.target.value);
      syncFilmstripSourceOptions();
      updateViewer();
    }
    if (event.target.matches('.noise-source-card [data-field="noise_type"]')) {
      const card = event.target.closest(".noise-source-card");
      const title = card?.querySelector(".source-card-heading strong");
      if (title) title.textContent = `${noiseTypeLabel(event.target.value)} noise`;
      applySourceCardColor(card, event.target.value);
      syncFilmstripSourceOptions();
      updateViewer();
    }
    if (event.target.matches('[data-element-field="is_jitter"]')) {
      setFilmstripElementMode(event.target);
      return;
    }
    if (event.target.closest?.(".filmstrip-row")) {
      state.design.protocol.trial_strips = collectTrialStrips();
      updateFilmstripCounts();
    }
  });
}

function reportError(error) {
  console.error(error);
  showToast(error.message || String(error));
}

loadApiBase();
loadResizableLayoutSettings();
enforceExternalLinkTargets();
renderHardwarePixelArt();
wireEvents();
initializePageTabs();
loadState().catch(reportError);
