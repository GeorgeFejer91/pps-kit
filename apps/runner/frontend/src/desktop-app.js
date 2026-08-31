import {
  ALL_ACTIONS,
  DEFAULT_REMOTE_SCOPES,
  SCOPES,
  intersectScopes,
  requiredScope,
} from "./domain/runner-contract.js";
import { selectRunnerAdapter } from "./api/runner-api.js";
import { PpsPublicBeacon } from "./remote/vdo-beacon.js";
import { PpsVdoTransport } from "./remote/vdo-transport.js";
import {
  BrspControllerSession,
  BrspTargetSession,
  remoteActionsForTarget,
} from "./remote/websocket-session.js";
import { renderQrCode } from "./ui/qr-code.js";

const api = selectRunnerAdapter();
const elements = Object.fromEntries([...document.querySelectorAll("[id]")].map((element) => [element.id, element]));
const outboundActionButtons = [...document.querySelectorAll("[data-controller-action]")];
const MAX_PENDING_NATIVE_COMMANDS = 32;

let snapshot = null;
let preparedPlan = null;
let preparedExecution = null;
let preparedAudio = null;
let remoteStatus = null;
let invitationUrl = "";
let toastTimer = null;
let pollTimer = null;

let inboundBeacon = null;
let pendingInboundRequest = null;
let inboundPrivateTarget = null;
let inboundBeaconOwnsActivation = false;

let outboundBeacon = null;
let outboundBeaconRequestId = "";
let outboundSelectedStreamId = "";
let outboundPrivateOffer = null;
let outboundController = null;

function text(id, value, fallback = "—") {
  const element = elements[id];
  if (element) element.textContent = value === undefined || value === null || value === "" ? fallback : String(value);
}

function titleCase(value) {
  return String(value || "unknown").replaceAll("_", " ").replace(/\b\w/gu, (letter) => letter.toUpperCase());
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function showToast(message, { error = false } = {}) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("is-error", error);
  elements.toast.classList.add("is-visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("is-visible"), 4_000);
}

function normalizedSnapshot(result) {
  return result?.snapshot ?? result;
}

function planValue(plan, camelName, snakeName) {
  return plan?.[camelName] ?? plan?.[snakeName];
}

function renderPreparedAudio(nextPreparation) {
  const candidate = nextPreparation && typeof nextPreparation === "object" ? nextPreparation : null;
  const schema = candidate?.schema;
  const scope = planValue(candidate, "preparationScope", "preparation_scope");
  const qualification = planValue(candidate, "outputQualification", "output_qualification");
  const blockOrdinal = Number(planValue(candidate, "blockOrdinal", "block_ordinal"));
  const sampleRate = Number(planValue(candidate, "sampleRateHz", "sample_rate_hz"));
  const channels = Number(planValue(candidate, "sourceChannels", "source_channels"));
  const layout = planValue(candidate, "sourceChannelLayout", "source_channel_layout");
  const frames = Number(candidate?.frames);
  const decodedBytes = Number(planValue(candidate, "decodedBytes", "decoded_bytes"));
  const capacity = Number(planValue(candidate, "cacheCapacityBlocks", "cache_capacity_blocks"));
  const byteBudget = Number(planValue(candidate, "cacheByteBudget", "cache_byte_budget"));
  const valid = Boolean(candidate)
    && schema === "pps-runner-prepared-audio-summary.v1"
    && scope === "pcm-cache-only"
    && qualification === "unqualified"
    && candidate.executable === false
    && blockOrdinal === 0
    && Number.isSafeInteger(sampleRate) && sampleRate > 0
    && [2, 3].includes(channels)
    && ["legacy-study5-tactile-audio", "binaural-left-right-tactile"].includes(layout)
    && Number.isSafeInteger(frames) && frames >= 0
    && Number.isSafeInteger(decodedBytes) && decodedBytes >= 0
    && capacity === 1
    && byteBudget === 1280 * 1024 * 1024
    && decodedBytes <= byteBudget;
  preparedAudio = valid ? candidate : null;
  text("prepared-audio-status", preparedAudio ? "Prepared · output disabled" : "Not prepared");
  text(
    "prepared-audio-detail",
    preparedAudio
      ? `Block 1 is content-bound in the one-block native PCM cache: ${frames.toLocaleString()} frames at ${sampleRate.toLocaleString()} Hz, ${channels} source channels (${layout}), ${(decodedBytes / (1024 * 1024)).toFixed(2)} MiB. Output qualification: ${qualification}; executable: no.`
      : preparedExecution
        ? "Prepare the first verified WAV into the bounded native PCM cache. This does not open an output device, route channels, arm, or execute the experiment."
        : "Native PCM preparation is unavailable until the first schedule is inspected.",
  );
  return !candidate || valid;
}

function renderPreparedExecution(nextInspection) {
  const candidate = nextInspection && typeof nextInspection === "object" ? nextInspection : null;
  const eventCount = Number(planValue(candidate, "eventCount", "event_count"));
  const trialCount = Number(planValue(candidate, "trialRowCount", "trial_row_count"));
  const blockCount = Number(planValue(candidate, "blockCount", "block_count"));
  const encodedBytes = Number(planValue(candidate, "encodedBytes", "encoded_bytes"));
  const scope = planValue(candidate, "inspectionScope", "inspection_scope");
  const qualification = planValue(candidate, "timingQualification", "timing_qualification");
  const blocks = candidate?.blocks;
  const valid = Boolean(candidate)
    && [eventCount, trialCount, blockCount, encodedBytes]
      .every((value) => Number.isSafeInteger(value) && value >= 0)
    && encodedBytes <= 32 * 1024 * 1024
    && Array.isArray(blocks)
    && blocks.length === blockCount
    && scope === "schedule-only"
    && qualification === "unqualified"
    && candidate.executable === false;
  preparedExecution = valid ? candidate : null;
  renderPreparedAudio(null);
  text("execution-inspection-status", preparedExecution ? "Compiled · inspection only" : "Not compiled");
  text("execution-event-count", preparedExecution && Number.isSafeInteger(eventCount) ? eventCount : null);
  text(
    "execution-inspection-detail",
    preparedExecution
      ? `${blockCount} block${blockCount === 1 ? "" : "s"}, ${trialCount} trial rows, and ${eventCount} sample-indexed events compiled in manifest order (${encodedBytes.toLocaleString()} encoded bytes retained natively). Scope: ${scope}; timing: ${qualification}; executable: no.`
      : preparedPlan
        ? "Compile the retained package with the Rust schedule oracle. This inspection does not arm outputs or authorize execution."
        : "Schedule inspection is unavailable until a real prepared session is selected.",
  );
  return !candidate || valid;
}

function renderPreparedPlan(nextPlan) {
  preparedPlan = nextPlan && typeof nextPlan === "object" ? nextPlan : null;
  renderPreparedExecution(null);
  const blocks = Array.isArray(preparedPlan?.blocks) ? preparedPlan.blocks : [];
  text("package-block-count", preparedPlan ? blocks.length : null);
  text("package-mode", preparedPlan ? planValue(preparedPlan, "executionMode", "execution_mode") : null);
  elements["package-block-list"].replaceChildren(...blocks.map((block) => {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    const details = document.createElement("span");
    label.textContent = `${block.index}. ${block.label}`;
    const trialCount = Number(planValue(block, "trialCount", "trial_count")) || 0;
    const duration = Number(planValue(block, "durationS", "duration_s")) || 0;
    details.textContent = `${trialCount} trials · ${formatDuration(duration)}`;
    item.append(label, details);
    return item;
  }));
  text(
    "package-detail",
    preparedPlan
      ? `${blocks.length} ordered block${blocks.length === 1 ? "" : "s"} passed native V1 provenance checks. Playback remains disabled until the Rust execution adapter is ready.`
      : "The native verifier checks the V1 manifest, ordered block files, source hashes, and trial counts before adoption.",
  );
}

function remoteSessionId(status = remoteStatus) {
  return status?.sessionId ?? status?.session_id ?? "";
}

function remoteAllowAbort(status = remoteStatus) {
  return Boolean(status?.allowAbort ?? status?.allow_abort);
}

function remoteEnabled(status = remoteStatus) {
  return Boolean(status?.enabled);
}

function remoteControllerConnected(status = remoteStatus) {
  return Boolean(status?.controllerConnected ?? status?.controller_connected);
}

function nativePublicationAuthorized(target) {
  const expiry = target?.remoteSnapshot?.safety?.lease_expires_at_unix_ms;
  return Boolean(target?.nativeClaimReceipt)
    && target?.remoteSnapshot?.schema === "pps-runner-public-snapshot.v1"
    && Number.isSafeInteger(expiry)
    && Date.now() < expiry;
}

function availableNativeScopes() {
  const scopes = [...DEFAULT_REMOTE_SCOPES];
  if (remoteAllowAbort()) scopes.push(SCOPES.ABORT);
  return [...new Set(scopes)].sort();
}

function updateInboundPolicyUi() {
  const armed = Boolean(snapshot?.safety?.local_armed);
  const enabled = remoteEnabled();
  const native = api.kind === "tauri-native";
  const hasRequest = Boolean(pendingInboundRequest);
  const connected = remoteControllerConnected();
  const canApprove = native && enabled && armed && hasRequest && !connected && !inboundPrivateTarget;
  elements["desktop-beacon-start"].disabled = !native || Boolean(inboundBeacon) || Boolean(inboundPrivateTarget);
  elements["desktop-beacon-stop"].disabled = !inboundBeacon && !inboundPrivateTarget;
  elements["desktop-request-approve"].disabled = !canApprove;
  if (!native) {
    text("desktop-request-policy", "Inbound native control is unavailable in ordinary-browser preview mode.");
  } else if (!enabled) {
    text("desktop-request-policy", "Advertise this runner can enable VDO-only authority without opening a LAN listener.");
  } else if (!armed) {
    text("desktop-request-policy", "Arm the target locally before approving a controller.");
  } else if (connected) {
    text("desktop-request-policy", "Another controller already owns the native target.");
  } else if (inboundPrivateTarget) {
    text("desktop-request-policy", "A private controller session already owns this target.");
  } else {
    text("desktop-request-policy", "Local remote-enable and arm policy is satisfied. Review scopes before approval.");
  }
}

function renderSnapshot(next) {
  if (!next || typeof next !== "object") return;
  snapshot = next;
  const phase = next.run?.phase ?? "unknown";
  const participant = next.setup?.participant_code || next.identity?.participant_id || "Not set";
  text("participant-chip", participant);
  text("part-chip", next.part?.selected_part ? `Part ${next.part.selected_part}` : "—");
  text("state-chip", titleCase(phase));
  text("run-heading", next.run?.state_label || titleCase(phase));
  text("run-progress", next.run?.progress_label, "Waiting for target state.");
  text("event-label", next.run?.event_label, "No current event");
  text("block-label", next.active_block?.active ? next.active_block.block_label : "No active block");
  const elapsed = Number(next.active_block?.elapsed_s) || 0;
  const duration = Number(next.active_block?.duration_s) || 0;
  text("block-time", `${formatDuration(elapsed)} / ${formatDuration(duration)}`);
  elements["block-progress"].style.width = `${duration > 0 ? Math.min(100, elapsed / duration * 100) : 0}%`;

  text("setup-badge", next.setup?.ready ? "Ready" : "Not submitted");
  elements["setup-badge"].dataset.tone = next.setup?.ready ? "ready" : "";
  if (document.activeElement !== elements["participant-code"]) elements["participant-code"].value = next.setup?.participant_code || "";
  if (document.activeElement !== elements["participant-age"]) elements["participant-age"].value = next.setup?.age ?? "";
  if (document.activeElement !== elements["participant-handedness"]) elements["participant-handedness"].value = next.setup?.handedness === "unspecified" ? "" : (next.setup?.handedness || "");
  if (document.activeElement !== elements["participant-gender"]) elements["participant-gender"].value = next.setup?.gender === "unspecified" ? "" : (next.setup?.gender || "");
  elements["name-sharing"].checked = Boolean(next.setup?.name_sharing_opt_in);

  text("package-badge", next.package_verified ? "Verified" : "Unverified");
  elements["package-badge"].dataset.tone = next.package_verified ? "ready" : "";
  text("package-label", next.package_label, "No package loaded.");
  const preparedSessionId = planValue(preparedPlan, "sessionId", "session_id");
  if (preparedPlan && preparedSessionId !== next.identity?.session_id) renderPreparedPlan(null);
  text("audio-route", next.safety?.audio_route_ready ? "Ready" : "Not ready");
  text("local-armed", next.safety?.local_armed ? "Yes" : "No");
  text("lsl-ready", next.safety?.lsl_ready ? "Ready" : "Not ready");
  text("capture-ready", next.safety?.capture_started ? "Started" : "Not started");
  text("session-id", next.identity?.session_id);
  text("package-part", next.part?.current_package_part ? `Part ${next.part.current_package_part}` : "—");
  text("revision", next.revision ?? 0);
  text("audit-events", next.audit_event_count ?? 0);
  text("last-note", next.last_note, "None");

  const allowed = new Set(next.allowed_actions || []);
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.disabled = !allowed.has(button.dataset.action);
  });
  elements["allowed-actions"].replaceChildren(...[...allowed].map((action) => {
    const token = document.createElement("span");
    token.textContent = action;
    return token;
  }));
  const active = ["instruction_gate", "running", "paused", "stopping"].includes(phase);
  const invalidatesPreparedAudio = active
    || ["completed", "interrupted", "error"].includes(phase)
    || !next.package_verified
    || !preparedExecution;
  if (preparedAudio && invalidatesPreparedAudio) renderPreparedAudio(null);
  elements["select-session-manifest"].disabled = api.kind !== "tauri-native" || active;
  elements["select-session-manifest"].title = api.kind === "tauri-native"
    ? "Select and verify a pps-run-session.v1 manifest locally"
    : "Prepared-session selection is available in the native Tauri app";
  elements["inspect-prepared-execution"].disabled = api.kind !== "tauri-native" || !preparedPlan || active;
  elements["inspect-prepared-execution"].title = api.kind === "tauri-native"
    ? "Reverify the retained package and compile a path-free schedule inspection"
    : "Rust schedule inspection is available in the native Tauri app";
  elements["prepare-first-audio-block"].disabled = api.kind !== "tauri-native"
    || !preparedExecution
    || active
    || Boolean(preparedAudio);
  elements["prepare-first-audio-block"].title = api.kind === "tauri-native"
    ? "Content-bind and decode the first verified WAV into the one-block native PCM cache"
    : "Native audio preparation is available in the Tauri app";
  updateInboundPolicyUi();

  if (inboundPrivateTarget?.nativeClaimReceipt && !next.safety?.local_armed) {
    void stopInboundNetworking("local_target_disarmed");
  }
}

function readRemoteUrl(status) {
  return status?.controllerUrl ?? status?.controller_url ?? status?.invitation_url ?? status?.invite_url ?? status?.pairing_url ?? status?.invitationUrl ?? "";
}

async function renderRemote(next) {
  if (!next || typeof next !== "object") return;
  remoteStatus = next;
  const enabled = remoteEnabled(next);
  const serverAvailable = Boolean(next.server_available ?? next.serverAvailable);
  const serverError = next.server_error ?? next.serverError ?? "";
  const connected = remoteControllerConnected(next);
  if (!enabled) inboundBeaconOwnsActivation = false;
  elements["remote-enabled"].checked = enabled;
  elements["remote-allow-abort"].checked = remoteAllowAbort(next);
  text("remote-state-badge", connected ? "Controller ready" : enabled ? "Enabled" : "Disabled");
  elements["remote-state-badge"].dataset.tone = connected ? "ready" : "";
  text(
    "remote-detail",
    serverError || next.status_message || next.message,
    enabled
      ? "Native remote authority is enabled. Public discovery remains off until Advertise this runner is pressed."
      : "Remote networking and native remote authority are inert until explicitly enabled.",
  );
  text("remote-controller", next.controller_id ?? next.controllerId, "None");
  const scopes = next.granted_scopes ?? next.grantedScopes ?? [];
  text("remote-scopes", Array.isArray(scopes) && scopes.length ? scopes.join(", ") : "None");
  text("remote-route", connected ? "Rust-owned remote reducer" : enabled ? "Enabled; no controller" : "Local-only");

  invitationUrl = readRemoteUrl(next);
  await renderQrCode(elements["pairing-qr"], invitationUrl);
  elements["pairing-placeholder"].hidden = Boolean(invitationUrl);
  elements["copy-invite"].disabled = !invitationUrl;
  text("pairing-summary", invitationUrl
    ? `Fresh legacy LAN invitation for ${next.target_id ?? next.targetId ?? "this runner"}. The secret remains in the fragment.`
    : serverAvailable
      ? "Remote authority is disabled. No active invitation is exposed."
      : "The website beacon below does not expose the app's local port or private pairing secret.");

  if (inboundPrivateTarget && (!enabled || remoteSessionId(next) !== inboundPrivateTarget.sessionId)) {
    void stopInboundPrivateTarget("remote_activation_changed");
  }
  updateInboundPolicyUi();
}

async function refreshSnapshot() {
  renderSnapshot(normalizedSnapshot(await api.snapshot()));
}

async function refreshRemote() {
  await renderRemote(await api.remoteStatus());
}

async function dispatch(action, args = {}) {
  const result = await api.dispatch(action, args);
  renderSnapshot(normalizedSnapshot(result));
  if (result?.status === "rejected") throw new Error(result.reason || `${action} was rejected.`);
  showToast(`${action} applied by the native target.`);
  return result;
}

function argsForAction(action, sourceSnapshot = snapshot) {
  if (action === "part.start") {
    return { part_number: sourceSnapshot?.part?.selected_part ?? sourceSnapshot?.part?.available_parts?.[0] ?? 1 };
  }
  if (action === "instruction.continue") {
    return { gate_id: sourceSnapshot?.instruction_gate?.gate_id ?? "" };
  }
  return {};
}

function inboundVdoTransport({ room, secret, targetId }) {
  return new PpsVdoTransport({
    role: "target",
    room,
    sharedSecret: secret,
    label: `PPS desktop target ${targetId.slice(-8)}`,
  });
}

function queueNativeControl(target, operation) {
  const queued = target.nativeControlTail.then(async () => {
    if (target !== inboundPrivateTarget || target.stopping || target.failureHandled) {
      throw new Error("The private controller no longer owns this target.");
    }
    const receipt = await target.claimPromise;
    if (target !== inboundPrivateTarget || target.stopping || target.failureHandled) {
      throw new Error("The private controller no longer owns this target.");
    }
    return operation(receipt);
  });
  target.nativeControlTail = queued;
  return queued;
}

function takeCommandOperation(target, commandId) {
  const queued = target.commandOperations.get(commandId) ?? [];
  const operation = queued.shift();
  if (queued.length) target.commandOperations.set(commandId, queued);
  else target.commandOperations.delete(commandId);
  if (!operation) throw new Error("The authenticated BRSP command operation is unavailable.");
  target.pendingNativeCommandCount = Math.max(0, target.pendingNativeCommandCount - 1);
  return operation;
}

function failInboundAuthority(target, error) {
  if (target !== inboundPrivateTarget || target.stopping || target.failureHandled) return;
  target.failureHandled = true;
  text("desktop-beacon-status", "Authority error");
  elements["desktop-beacon-status"].dataset.tone = "danger";
  showToast(error instanceof Error ? error.message : String(error), { error: true });
  void stopInboundNetworking("native_authority_failed");
}

function observeInboundRenewal(target, promise) {
  void promise.then((receipt) => {
    if (target !== inboundPrivateTarget || target.stopping) return;
    target.nativeClaimReceipt = receipt;
    target.remoteSnapshot = receipt.snapshot;
    text("desktop-private-lease", `Rust lease until ${new Date(receipt.leaseExpiresAtUnixMs).toLocaleTimeString()}`);
    target.session.publishState(target.remoteSnapshot);
    void refreshSnapshot().catch((error) => failInboundAuthority(target, error));
  }).catch((error) => failInboundAuthority(target, error));
}

function acceptedInboundControl(target, envelope) {
  if (target !== inboundPrivateTarget || target.stopping || !target.claimPromise) return false;
  if (envelope.type === "command") {
    if (target.pendingNativeCommandCount >= MAX_PENDING_NATIVE_COMMANDS) return false;
    if (!target.actions.includes(envelope.body.action)
      || requiredScope(envelope.body.action) !== envelope.body.scope) return false;
    const commandId = envelope.body.commandId;
    const operations = target.commandOperations.get(commandId) ?? [];
    const operation = queueNativeControl(target, (receipt) => api.remoteSessionDispatch({
      sessionId: target.sessionId,
      ownerToken: receipt.ownerToken,
      controlSequence: envelope.sequence,
      command: envelope.body,
    }));
    operations.push(operation);
    target.commandOperations.set(commandId, operations);
    target.pendingNativeCommandCount += 1;
    void operation.catch((error) => failInboundAuthority(target, error));
    return operation;
  }
  if (envelope.type === "snapshot-request" || envelope.type === "error") {
    const renewal = queueNativeControl(target, (receipt) => api.remoteSessionRenew({
      sessionId: target.sessionId,
      ownerToken: receipt.ownerToken,
      controlSequence: envelope.sequence,
    }));
    observeInboundRenewal(target, renewal);
    return renewal;
  }
  return true;
}

async function applyInboundCommand(target, request) {
  const applied = await takeCommandOperation(target, request.id);
  if (target !== inboundPrivateTarget || target.stopping) throw new Error("The private controller no longer owns this target.");
  target.remoteSnapshot = applied.snapshot;
  void refreshSnapshot().catch((error) => failInboundAuthority(target, error));
  return {
    status: applied.status,
    reason: applied.reason,
    acceptedRevision: applied.accepted_revision,
    resultingRevision: applied.resulting_revision,
    snapshot: applied.snapshot,
  };
}

function bindInboundPrivateSession(target) {
  const { session } = target;
  session.addEventListener("phasechange", (event) => {
    if (target !== inboundPrivateTarget) return;
    text("desktop-beacon-status", titleCase(event.detail.phase));
    text("desktop-beacon-detail", event.detail.message, "Private BRSP session is changing state.");
  });
  session.addEventListener("ready", () => {
    if (target !== inboundPrivateTarget || target.claimPromise) return;
    if (Date.now() >= target.offerExpiresUnixMs) {
      void stopInboundNetworking("private_offer_expired");
      return;
    }
    const status = session.status();
    target.claimPromise = api.remoteSessionClaim({
      sessionId: target.sessionId,
      controllerId: status.controllerId,
      acceptedScopes: status.grantedScopes,
      readySequence: session.connection.remoteControlSequence,
    });
    void target.claimPromise.then((receipt) => {
      if (target !== inboundPrivateTarget || target.stopping) return;
      if (target.offerExpiryTimer !== null) clearTimeout(target.offerExpiryTimer);
      target.offerExpiryTimer = null;
      target.nativeClaimReceipt = receipt;
      target.remoteSnapshot = receipt.snapshot;
      text("desktop-beacon-status", "Private controller ready");
      elements["desktop-beacon-status"].dataset.tone = "ready";
      text("desktop-beacon-detail", `Authenticated controller ${receipt.controllerId} is bound to Rust authority.`);
      text("desktop-private-lease", `Rust lease until ${new Date(receipt.leaseExpiresAtUnixMs).toLocaleTimeString()}`);
      session.publishState(target.remoteSnapshot);
      void refreshSnapshot().catch((error) => failInboundAuthority(target, error));
      void stopInboundBeacon({ preserveStatus: true });
    }).catch((error) => failInboundAuthority(target, error));
  });
  session.addEventListener("transportstatus", (event) => {
    if (target === inboundPrivateTarget && event.detail?.message) text("desktop-private-route", `VDO data-only · ${event.detail.message}`);
  });
  session.addEventListener("quality", (event) => {
    if (target !== inboundPrivateTarget) return;
    const rtt = Number.isFinite(event.detail?.rttMs) ? ` · ${event.detail.rttMs} ms RTT` : "";
    text("desktop-private-route", `VDO data-only · ${event.detail?.route ?? "unknown"}${rtt}`);
  });
  session.addEventListener("protocolerror", (event) => failInboundAuthority(target, new Error(event.detail?.message || "Private BRSP protocol error.")));
  session.addEventListener("commandhandled", (event) => {
    if (target !== inboundPrivateTarget) return;
    const commandId = event.detail?.command?.commandId;
    const unused = target.commandOperations.get(commandId) ?? [];
    target.pendingNativeCommandCount = Math.max(0, target.pendingNativeCommandCount - unused.length);
    target.commandOperations.delete(commandId);
  });
  session.addEventListener("leaseexpired", (event) => {
    if (target === inboundPrivateTarget) void stopInboundNetworking(event.detail?.reason || "controller_lease_expired");
  });
}

async function startInboundPrivateTarget(offer) {
  await stopInboundPrivateTarget("private_target_replaced");
  const target = {
    sessionId: offer.sessionId,
    commandOperations: new Map(),
    pendingNativeCommandCount: 0,
    nativeControlTail: Promise.resolve(),
    offerExpiresUnixMs: offer.expiresUnixMs,
    claimPromise: null,
    nativeClaimReceipt: null,
    remoteSnapshot: null,
    failureHandled: false,
    stopping: false,
    offerExpiryTimer: null,
    session: null,
  };
  const actions = remoteActionsForTarget(ALL_ACTIONS, offer.acceptedScopes);
  target.actions = actions;
  target.session = new BrspTargetSession({
    transport: inboundVdoTransport({ room: offer.room, secret: offer.secret, targetId: offer.targetId }),
    secret: offer.secret,
    targetId: offer.targetId,
    sessionId: offer.sessionId,
    availableScopes: offer.acceptedScopes,
    actions,
    // Before native claim, publication is closed. After claim, BRSP may only
    // observe the Rust-projected public snapshot retained on this target; the
    // full operator snapshot remains local to the Tauri UI.
    getSnapshot: () => target.remoteSnapshot ?? snapshot,
    applyCommand: (request) => applyInboundCommand(target, request),
    applicationOwnsTransitionValidation: true,
    stateHeartbeatEnabled: false,
    canPublishTargetState: () => nativePublicationAuthorized(target),
    onAcceptedControllerControl: (envelope) => acceptedInboundControl(target, envelope),
    onLeaseExpired: ({ reason }) => {
      if (target === inboundPrivateTarget) void stopInboundNetworking(reason);
    },
  });
  inboundPrivateTarget = target;
  bindInboundPrivateSession(target);
  updateInboundPolicyUi();
  text("desktop-private-route", "VDO data-only · starting private target");
  const remainingOfferMs = Math.max(0, offer.expiresUnixMs - Date.now());
  target.offerExpiryTimer = setTimeout(() => {
    target.offerExpiryTimer = null;
    if (target === inboundPrivateTarget && !target.nativeClaimReceipt) {
      void stopInboundNetworking("private_offer_expired");
    }
  }, remainingOfferMs);
  await Promise.resolve(target.session.connect());
}

async function stopInboundPrivateTarget(reason = "local_stop") {
  const target = inboundPrivateTarget;
  if (!target) return;
  inboundPrivateTarget = null;
  target.stopping = true;
  if (target.offerExpiryTimer !== null) clearTimeout(target.offerExpiryTimer);
  target.offerExpiryTimer = null;
  target.commandOperations.clear();
  target.pendingNativeCommandCount = 0;
  target.session.stop();
  text("desktop-private-route", "Not connected");
  text("desktop-private-lease", "None");
  updateInboundPolicyUi();
  try {
    const receipt = target.nativeClaimReceipt ?? await target.claimPromise;
    if (receipt?.ownerToken) {
      await api.remoteSessionRevoke({ sessionId: target.sessionId, ownerToken: receipt.ownerToken });
      await refreshSnapshot();
    }
  } catch {
    // Rotation, disable, lease expiry, or app teardown can invalidate this exact owner first.
  }
  if (reason !== "local_stop" && reason !== "private_target_replaced") {
    text("desktop-beacon-detail", `Private controller stopped: ${titleCase(reason)}.`);
  }
}

function renderPendingInboundRequest() {
  const requests = inboundBeacon?.pendingPairingRequests() ?? [];
  pendingInboundRequest = requests[0] ?? null;
  elements["desktop-pairing-request"].hidden = !pendingInboundRequest;
  if (pendingInboundRequest) {
    text("desktop-request-label", pendingInboundRequest.label, "Browser controller");
    text("desktop-request-scopes", pendingInboundRequest.requestedScopes.join(", "), "None");
  }
  updateInboundPolicyUi();
}

function bindInboundBeacon(beacon) {
  beacon.addEventListener("status", (event) => {
    if (beacon !== inboundBeacon) return;
    text("desktop-beacon-status", event.detail.error ? "Beacon error" : titleCase(event.detail.phase));
    elements["desktop-beacon-status"].dataset.tone = event.detail.error ? "danger" : "";
    text("desktop-beacon-detail", event.detail.message);
  });
  beacon.addEventListener("pairingrequest", () => {
    if (inboundPrivateTarget) {
      for (const request of beacon.pendingPairingRequests()) beacon.rejectPairing(request.requestId, "target_busy");
      return;
    }
    renderPendingInboundRequest();
    showToast("A public controller requests private access. Review its label and scopes locally.");
  });
  beacon.addEventListener("pairingcancelled", renderPendingInboundRequest);
  beacon.addEventListener("pairingrejected", renderPendingInboundRequest);
  beacon.addEventListener("protocolerror", (event) => showToast(event.detail.message, { error: true }));
}

async function startInboundBeacon() {
  if (api.kind !== "tauri-native") throw new Error("Inbound desktop control requires the native Tauri runner.");
  await stopInboundBeacon();
  if (!remoteEnabled()) {
    const activated = await api.configureRemote({
      enabled: true,
      allowAbort: elements["remote-allow-abort"].checked,
      lanListener: false,
    });
    inboundBeaconOwnsActivation = true;
    await renderRemote(activated);
  }
  const beacon = new PpsPublicBeacon({ role: "target", label: "PPS desktop experiment runner" });
  inboundBeacon = beacon;
  bindInboundBeacon(beacon);
  updateInboundPolicyUi();
  await beacon.startAdvertising();
}

async function stopInboundBeacon({ preserveStatus = false } = {}) {
  const beacon = inboundBeacon;
  inboundBeacon = null;
  pendingInboundRequest = null;
  elements["desktop-pairing-request"].hidden = true;
  updateInboundPolicyUi();
  if (beacon) await beacon.stop();
  if (!preserveStatus && !inboundPrivateTarget) {
    text("desktop-beacon-status", "Beacon off");
    text(
      "desktop-beacon-detail",
      remoteEnabled()
        ? "Remote authority enabled; public discovery is off."
        : "Press Advertise this runner to enable VDO-only authority without a LAN listener.",
    );
  }
}

async function stopInboundNetworking(reason = "local_stop", { disableOwnedActivation = true } = {}) {
  const disableActivation = disableOwnedActivation && inboundBeaconOwnsActivation;
  await Promise.allSettled([stopInboundBeacon(), stopInboundPrivateTarget(reason)]);
  if (disableActivation) {
    inboundBeaconOwnsActivation = false;
    try {
      await renderRemote(await api.configureRemote({ enabled: false, allowAbort: false, lanListener: false }));
    } catch {
      // Page teardown or an already-rotated activation can make best-effort disable unavailable.
    }
  }
}

function renderOutboundTargets(targets = []) {
  const list = elements["desktop-controller-targets"];
  list.replaceChildren();
  if (!targets.length) {
    const empty = document.createElement("p");
    empty.className = "subtle";
    empty.textContent = outboundBeacon ? "No public PPS targets are currently visible." : "Press Browse to list public PPS targets.";
    list.append(empty);
    return;
  }
  for (const target of targets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "beacon-target-button";
    button.dataset.streamId = target.streamId;
    button.setAttribute("aria-pressed", String(target.streamId === outboundSelectedStreamId));
    const name = document.createElement("strong");
    name.textContent = target.label;
    const identifier = document.createElement("span");
    identifier.textContent = `Unverified public ID · ${target.streamId.slice(-12)}`;
    button.append(name, identifier);
    button.addEventListener("click", async () => {
      try {
        outboundSelectedStreamId = target.streamId;
        renderOutboundTargets(targets);
        await outboundBeacon?.selectTarget(target.streamId);
      } catch (error) {
        showToast(error.message, { error: true });
      }
    });
    list.append(button);
  }
}

function updateOutboundControls() {
  const session = outboundController?.session;
  const current = session?.snapshot;
  const ready = session?.phase === "ready";
  const busy = session?.status().reliableCommandBusy === true;
  const granted = new Set(session?.grantedScopes ?? []);
  const allowed = new Set(current?.allowed_actions ?? []);
  for (const button of outboundActionButtons) {
    const action = button.dataset.controllerAction;
    button.disabled = !ready || busy || !allowed.has(action) || !granted.has(requiredScope(action));
  }
  elements["desktop-controller-disconnect"].disabled = !outboundController;
}

function renderOutboundSnapshot(next) {
  if (!next) return;
  text("desktop-controller-target", next.package_label || next.target_id);
  text("desktop-controller-revision", next.revision);
  updateOutboundControls();
}

function bindOutboundSession(controller) {
  const { session } = controller;
  session.addEventListener("phasechange", (event) => {
    if (controller !== outboundController) return;
    text("desktop-controller-status", titleCase(event.detail.phase));
    updateOutboundControls();
  });
  session.addEventListener("ready", () => {
    if (controller !== outboundController) return;
    text("desktop-controller-status", "Private controller ready");
    elements["desktop-controller-status"].dataset.tone = "ready";
    text("desktop-controller-selection", "Mutual BRSP proof complete. Controls follow target-returned state only.");
    updateOutboundControls();
  });
  session.addEventListener("snapshot", (event) => {
    if (controller === outboundController) renderOutboundSnapshot(event.detail.snapshot);
  });
  session.addEventListener("pendingchange", updateOutboundControls);
  session.addEventListener("commandapplied", (event) => {
    if (controller !== outboundController) return;
    const rejected = event.detail.status === "rejected";
    showToast(`${event.detail.action}: ${event.detail.reason}`, { error: rejected });
    updateOutboundControls();
  });
  session.addEventListener("transportstatus", (event) => {
    if (controller === outboundController && event.detail?.message) text("desktop-controller-route", `VDO data-only · ${event.detail.message}`);
  });
  session.addEventListener("quality", (event) => {
    if (controller !== outboundController) return;
    const rtt = Number.isFinite(event.detail?.rttMs) ? ` · ${event.detail.rttMs} ms RTT` : "";
    text("desktop-controller-route", `VDO data-only · ${event.detail?.route ?? "unknown"}${rtt}`);
  });
  session.addEventListener("protocolerror", (event) => {
    if (controller !== outboundController) return;
    showToast(event.detail?.message || "Outbound BRSP protocol error.", { error: true });
    void stopOutboundControllerSession();
  });
}

async function connectOutboundController() {
  const offer = outboundPrivateOffer;
  if (!offer) throw new Error("Request and receive a private target offer first.");
  if (offer.expiresUnixMs <= Date.now()) {
    outboundPrivateOffer = null;
    elements["desktop-controller-connect"].disabled = true;
    throw new Error("The private target offer expired. Browse and request again.");
  }
  await stopOutboundControllerSession();
  const controller = { offer, session: null };
  controller.session = new BrspControllerSession({
    transport: new PpsVdoTransport({
      role: "controller",
      room: offer.room,
      sharedSecret: offer.secret,
      label: "PPS desktop browser controller",
    }),
    secret: offer.secret,
    targetId: offer.targetId,
    sessionId: offer.sessionId,
    requestedScopes: offer.acceptedScopes,
  });
  outboundController = controller;
  bindOutboundSession(controller);
  elements["desktop-controller-connect"].disabled = true;
  elements["desktop-controller-disconnect"].disabled = false;
  text("desktop-controller-route", "VDO data-only · connecting");
  await Promise.resolve(controller.session.connect());
}

async function stopOutboundControllerSession() {
  const controller = outboundController;
  outboundController = null;
  if (controller) controller.session.stop();
  text("desktop-controller-route", "Not connected");
  text("desktop-controller-revision", "—");
  elements["desktop-controller-disconnect"].disabled = true;
  elements["desktop-controller-connect"].disabled = !outboundPrivateOffer;
  updateOutboundControls();
}

function bindOutboundBeacon(beacon) {
  beacon.addEventListener("status", (event) => {
    if (beacon !== outboundBeacon) return;
    text("desktop-controller-status", event.detail.error ? "Beacon error" : titleCase(event.detail.phase));
    elements["desktop-controller-status"].dataset.tone = event.detail.error ? "danger" : "";
  });
  beacon.addEventListener("targetschange", (event) => renderOutboundTargets(event.detail.targets));
  beacon.addEventListener("targetselected", (event) => {
    outboundSelectedStreamId = event.detail.streamId;
    text("desktop-controller-selection", `${event.detail.label} selected. Waiting for its public request channel.`);
  });
  beacon.addEventListener("peeropen", () => {
    elements["desktop-controller-request"].disabled = false;
    text("desktop-controller-selection", "Public request channel ready. The target still must approve locally.");
  });
  beacon.addEventListener("peerclose", () => {
    elements["desktop-controller-request"].disabled = true;
    text("desktop-controller-selection", "The selected target left. Stop and browse again.");
  });
  beacon.addEventListener("pairingrequested", (event) => {
    outboundBeaconRequestId = event.detail.requestId;
    elements["desktop-controller-request"].disabled = true;
    text("desktop-controller-selection", "Private access requested. Waiting for target-local approval.");
  });
  beacon.addEventListener("pairingoffer", (event) => {
    if (event.detail.requestId !== outboundBeaconRequestId) return;
    const offer = beacon.takePrivateOffer(event.detail.requestId);
    outboundBeaconRequestId = "";
    if (!offer) {
      showToast("The approved private offer expired before it could be loaded.", { error: true });
      return;
    }
    outboundPrivateOffer = offer;
    text("desktop-controller-target", offer.targetId);
    text("desktop-controller-status", "Private offer ready");
    elements["desktop-controller-status"].dataset.tone = "ready";
    text("desktop-controller-selection", "Target approved. Press Connect privately to perform mutual BRSP proof.");
    elements["desktop-controller-connect"].disabled = false;
    void stopOutboundBeacon({ preserveOffer: true, preserveStatus: true });
  });
  beacon.addEventListener("pairingrejected", (event) => {
    outboundBeaconRequestId = "";
    text("desktop-controller-selection", `Request not approved: ${titleCase(event.detail.reason)}.`);
    showToast("The target did not approve private access.", { error: true });
  });
  beacon.addEventListener("protocolerror", (event) => showToast(event.detail.message, { error: true }));
}

async function startOutboundBeacon() {
  await stopOutboundBeacon();
  await stopOutboundControllerSession();
  outboundPrivateOffer = null;
  const beacon = new PpsPublicBeacon({ role: "controller", label: "PPS desktop controller" });
  outboundBeacon = beacon;
  bindOutboundBeacon(beacon);
  elements["desktop-controller-browse"].disabled = true;
  elements["desktop-controller-stop"].disabled = false;
  renderOutboundTargets();
  await beacon.startBrowsing();
}

async function stopOutboundBeacon({ preserveOffer = false, preserveStatus = false } = {}) {
  const beacon = outboundBeacon;
  outboundBeacon = null;
  outboundBeaconRequestId = "";
  outboundSelectedStreamId = "";
  if (!preserveOffer) outboundPrivateOffer = null;
  elements["desktop-controller-browse"].disabled = false;
  elements["desktop-controller-stop"].disabled = true;
  elements["desktop-controller-request"].disabled = true;
  elements["desktop-controller-connect"].disabled = !outboundPrivateOffer || Boolean(outboundController);
  renderOutboundTargets();
  if (beacon) await beacon.stop();
  if (!preserveStatus && !outboundController) {
    text("desktop-controller-status", "Controller off");
    text("desktop-controller-selection", "No public target selected.");
  }
}

async function stopAllRemoteNetworking() {
  if (pollTimer !== null) clearInterval(pollTimer);
  pollTimer = null;
  await Promise.allSettled([
    stopInboundNetworking("page_or_app_closed"),
    stopOutboundBeacon(),
    stopOutboundControllerSession(),
  ]);
}

function bindTabs() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("is-active", active);
        candidate.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === button.dataset.tab));
    });
  });
}

function bindLocalActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      if (action === "run.abort" && !confirm("Abort the active run? This is logged as an interruption.")) return;
      button.disabled = true;
      try { await dispatch(action, argsForAction(action)); } catch (error) { showToast(error.message, { error: true }); }
      finally { if (snapshot) renderSnapshot(snapshot); }
    });
  });

  elements["select-session-manifest"].addEventListener("click", async () => {
    const button = elements["select-session-manifest"];
    button.disabled = true;
    try {
      const selection = await api.selectPreparedSession();
      renderSnapshot(normalizedSnapshot(selection));
      if (selection?.cancelled) {
        showToast("Prepared-session selection cancelled.");
        return;
      }
      renderPreparedPlan(selection?.summary);
      await refreshRemote();
      showToast("Prepared session verified and adopted by the native Rust authority.");
    } catch (error) {
      showToast(error.message, { error: true });
    } finally {
      if (snapshot) renderSnapshot(snapshot);
    }
  });

  elements["inspect-prepared-execution"].addEventListener("click", async () => {
    const button = elements["inspect-prepared-execution"];
    button.disabled = true;
    try {
      const inspection = await api.inspectPreparedExecution();
      if (!renderPreparedExecution(inspection)) {
        throw new Error("The native runner returned an invalid schedule-inspection summary.");
      }
      showToast("Rust schedules compiled for inspection. Audio and execution remain disabled.");
    } catch (error) {
      renderPreparedExecution(null);
      showToast(error.message, { error: true });
    } finally {
      if (snapshot) renderSnapshot(snapshot);
    }
  });

  elements["prepare-first-audio-block"].addEventListener("click", async () => {
    const button = elements["prepare-first-audio-block"];
    button.disabled = true;
    try {
      const prepared = await api.prepareFirstAudioBlock();
      if (!renderPreparedAudio(prepared)) {
        throw new Error("The native runner returned an invalid prepared-audio summary.");
      }
      showToast("First block content-bound in native PCM memory. Device output and execution remain disabled.");
    } catch (error) {
      renderPreparedAudio(null);
      showToast(error.message, { error: true });
    } finally {
      if (snapshot) renderSnapshot(snapshot);
    }
  });

  elements["setup-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    const args = {
      participant_code: elements["participant-code"].value,
      participant_name: elements["participant-name"].value,
      name_sharing_opt_in: elements["name-sharing"].checked,
      age: Number(elements["participant-age"].value),
      handedness: elements["participant-handedness"].value,
      gender: elements["participant-gender"].value,
      part_labels: snapshot?.setup?.part_labels ?? { "1": "Part 1", "2": "Part 2" },
    };
    try { await dispatch("setup.submit", args); } catch (error) { showToast(error.message, { error: true }); }
  });

  elements["note-button"].addEventListener("click", async () => {
    try {
      await dispatch("session.note", { text: elements["session-note"].value });
      elements["session-note"].value = "";
    } catch (error) { showToast(error.message, { error: true }); }
  });
}

function bindNativeRemoteControls() {
  elements["remote-apply"].addEventListener("click", async () => {
    const enabled = elements["remote-enabled"].checked;
    const allowAbort = elements["remote-allow-abort"].checked;
    try {
      if (inboundBeaconOwnsActivation || !enabled || enabled !== remoteEnabled() || allowAbort !== remoteAllowAbort()) {
        await stopInboundNetworking("remote_policy_changed", { disableOwnedActivation: true });
      }
      await renderRemote(await api.configureRemote({ enabled, allowAbort, lanListener: true }));
      showToast(enabled ? "Native remote authority enabled. Public discovery remains off." : "Remote authority disabled and inbound producers stopped.");
    } catch (error) { showToast(error.message, { error: true }); }
  });

  elements["rotate-pairing"].addEventListener("click", async () => {
    try {
      await stopInboundNetworking("pairing_rotated");
      await renderRemote(await api.rotatePairing());
      showToast("Pairing material rotated; older invitations and private owners are invalid.");
    } catch (error) { showToast(error.message, { error: true }); }
  });

  elements["copy-invite"].addEventListener("click", async () => {
    if (!invitationUrl) return;
    try {
      await navigator.clipboard.writeText(invitationUrl);
      showToast("Invitation copied. Treat it as a short-lived secret.");
    } catch { showToast("Clipboard access was denied by the system.", { error: true }); }
  });

  elements["desktop-beacon-start"].addEventListener("click", () => {
    void startInboundBeacon().catch(async (error) => {
      showToast(error.message, { error: true });
      await stopInboundNetworking("beacon_start_failed");
    });
  });
  elements["desktop-beacon-stop"].addEventListener("click", () => {
    void stopInboundNetworking("local_stop");
  });
  elements["desktop-request-deny"].addEventListener("click", () => {
    if (!pendingInboundRequest || !inboundBeacon) return;
    inboundBeacon.rejectPairing(pendingInboundRequest.requestId, "target_denied");
    renderPendingInboundRequest();
    showToast("Private access request denied.");
  });
  elements["desktop-request-approve"].addEventListener("click", async () => {
    const request = pendingInboundRequest;
    const beacon = inboundBeacon;
    if (!request || !beacon) return;
    try {
      if (api.kind !== "tauri-native" || !remoteEnabled() || !snapshot?.safety?.local_armed) {
        throw new Error("Remote authority must be enabled and the target locally armed before approval.");
      }
      if (remoteControllerConnected()) throw new Error("Another controller already owns the native target.");
      const acceptedScopes = intersectScopes(request.requestedScopes, availableNativeScopes());
      if (!acceptedScopes.length) throw new Error("The request contains no locally available scopes.");
      const sessionId = remoteSessionId();
      if (!sessionId) throw new Error("The current native remote activation has no session identifier.");
      const offer = beacon.approvePairing(request.requestId, {
        targetId: snapshot.target_id,
        sessionId,
        acceptedScopes,
        expiresUnixMs: Date.now() + 90_000,
      });
      pendingInboundRequest = null;
      elements["desktop-pairing-request"].hidden = true;
      await startInboundPrivateTarget(offer);
      text("desktop-beacon-detail", "Local approval sent. The private target is waiting for the controller's explicit Connect and BRSP proof.");
      showToast("Private desktop target started after local approval.");
    } catch (error) {
      showToast(error.message, { error: true });
      renderPendingInboundRequest();
    }
  });
}

function bindOutboundControllerControls() {
  elements["desktop-controller-browse"].addEventListener("click", () => {
    void startOutboundBeacon().catch(async (error) => {
      showToast(error.message, { error: true });
      await stopOutboundBeacon();
    });
  });
  elements["desktop-controller-stop"].addEventListener("click", () => {
    void stopOutboundBeacon();
  });
  elements["desktop-controller-request"].addEventListener("click", () => {
    try {
      outboundBeacon?.requestPairing({ requestedScopes: [...DEFAULT_REMOTE_SCOPES, SCOPES.ABORT].sort() });
    } catch (error) { showToast(error.message, { error: true }); }
  });
  elements["desktop-controller-connect"].addEventListener("click", () => {
    void connectOutboundController().catch((error) => showToast(error.message, { error: true }));
  });
  elements["desktop-controller-disconnect"].addEventListener("click", () => {
    void stopOutboundControllerSession();
  });
  for (const button of outboundActionButtons) {
    button.addEventListener("click", () => {
      const session = outboundController?.session;
      if (!session) return;
      try {
        session.sendCommand(button.dataset.controllerAction, argsForAction(button.dataset.controllerAction, session.snapshot));
        updateOutboundControls();
      } catch (error) { showToast(error.message, { error: true }); }
    });
  }
}

async function start() {
  bindTabs();
  bindLocalActions();
  bindNativeRemoteControls();
  bindOutboundControllerControls();
  renderOutboundTargets();
  updateInboundPolicyUi();
  try {
    const [initialSnapshot, initialRemote] = await Promise.all([api.snapshot(), api.remoteStatus()]);
    renderSnapshot(normalizedSnapshot(initialSnapshot));
    await renderRemote(initialRemote);
  } catch (error) {
    text("state-chip", "Native bridge unavailable");
    showToast(error.message, { error: true });
  }

  pollTimer = setInterval(() => {
    if (document.visibilityState !== "visible") return;
    void Promise.all([refreshSnapshot(), refreshRemote()]).catch(() => {});
  }, 1_000);
}

window.addEventListener("pagehide", () => {
  void stopAllRemoteNetworking();
}, { once: true });

void start();
