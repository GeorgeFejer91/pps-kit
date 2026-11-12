import {
  ACTION_SCOPE,
  DEFAULT_REMOTE_SCOPES,
  SCOPES,
  requiredScope,
  publicRunnerSnapshot,
} from "./domain/runner-contract.js";
import {
  allowedPhoneActions,
  applyPhoneAction,
  browserStudyStep,
  prepareBrowserStudy,
  createPhoneExperimentSnapshot,
  expirePhoneLease,
  recordBrowserTrial,
  setPhoneConnectionMetadata,
} from "./domain/phone-experiment-reducer.js";
import { BrowserOutputEngine, DEMO_AUDIO_MS, DEMO_DURATION_MS } from "./phone/browser-output-engine.js";
import { TapResponseWindow } from "./phone/tap-response.js";
import { loadPhoneStudy, phoneStudyCatalog, PhoneStudyPlayback } from "./phone/phone-study-playback.js";
import {
  createVdoInvitation,
  parseInvitation,
  stripInvitationMaterial,
  webSocketUrl,
} from "./remote/invitation.js";
import { createPairingSecret, createProtocolEpoch, createProtocolIdentity } from "./remote/protocol.js";
import { PpsVdoTransport, generateVdoRoomId } from "./remote/vdo-transport.js";
import { PpsPublicBeacon } from "./remote/vdo-beacon.js";
import { BrspControllerSession, BrspTargetSession } from "./remote/websocket-session.js";
import { installBrowserLifecycle } from "./remote/browser-lifecycle.js";
import { renderQrCode } from "./ui/qr-code.js";
import { bindRunnerControls, updateRemoteAttention } from "./ui/runner-controls.js";
import { initializeTextLayout } from "./ui/text-layout.js";

import { initializeSiteHeader } from "../../../../packages/pps-resources/assets/ui/site-header.mjs";
import { initializeTheme } from "../../../../packages/pps-resources/assets/ui/theme.mjs";

const themeToggle = document.getElementById("runner-theme-toggle");
initializeTheme(themeToggle);
initializeSiteHeader(document.querySelector(".site-tabs"), themeToggle);
initializeTextLayout();

const elements = Object.fromEntries([...document.querySelectorAll("[id]")].map((element) => [element.id, element]));
const outputEngine = new BrowserOutputEngine();
const responseWindow = new TapResponseWindow();
let trialStartMs = null;
let loadedStudy = null;
let studyLoading = false;
let armPending = false;
const studyBase = new URL("../assets/phone-studies/", location.href);
function reportOutputError(error) {
  applyPhone("target.disarm", {}, { source: "browser-output" });
  showToast(error.message, { error: true });
}

const studyPlayback = new PhoneStudyPlayback(outputEngine, {
  instruction: (label) => updateStudyStep(label),
  gate: (gate) => updateStudyStep(gate.label, gate),
  trial: (record, startMs, anchorMs, update) => {
    trialStartMs = startMs;
    if (anchorMs !== null) responseWindow.open(anchorMs, record.number);
    phoneSnapshot = recordBrowserTrial(phoneSnapshot, record, clock);
    appendEvent({ action: update ? "study.anchor" : "study.trial", ...record }, "browser-output");
    publishPhoneSnapshot();
  },
  complete: () => applyPhone("run.complete_demo", {}, { source: "browser-output" }),
  error: reportOutputError,
});
let controllerInvitation = null;
let controllerSession = null;
let controllerBeacon = null;
let controllerBeaconRequestId = "";
let targetBeacon = null;
let targetBeaconExpiry = null;
let pendingTargetRequest = null;
let phoneTarget = null;
let phoneSnapshot = null;
let targetInvitationUrl = "";
let eventLog = [];
let eventSequence = 0;
let toastTimer = null;
let browserActive = true;
let resumeController = false;

function clock() {
  return {
    unixMs: Date.now(),
    monotonicNs: Math.floor(performance.now() * 1_000_000),
  };
}

function text(id, value, fallback = "—") {
  const element = elements[id]?.querySelector(":scope > .icon-label") ?? elements[id];
  const label = value === undefined || value === null || value === "" ? fallback : String(value);
  if (element && element.textContent !== label) element.textContent = label;
}

function titleCase(value) {
  return String(value || "unknown").replaceAll("_", " ").replace(/\b\w/gu, (letter) => letter.toUpperCase());
}

function showToast(message, { error = false } = {}) {
  clearTimeout(toastTimer);
  const owner = document.querySelector(".runner-dialog[open] .dialog-body") ?? document.body;
  owner.append(elements["companion-toast"]);
  elements["companion-toast"].textContent = message;
  elements["companion-toast"].classList.toggle("is-error", error);
  elements["companion-toast"].classList.add("is-visible");
  toastTimer = setTimeout(() => elements["companion-toast"].classList.remove("is-visible"), 4_000);
}

function setConnectionStatus(phase, label = titleCase(phase)) {
  elements["companion-status"].dataset.phase = phase;
  text("companion-status", label);
}

function activateMode(mode) {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll("[data-beacon-role]").forEach((panel) => {
    panel.hidden = panel.dataset.beaconRole !== mode;
  });
  document.querySelectorAll("[data-mode-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.modePanel !== mode;
    panel.classList.toggle("is-active", !panel.hidden);
  });
}

function bindModeSwitch() {
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => activateMode(button.dataset.mode)));
}

function renderControllerSnapshot(snapshot) {
  if (!snapshot) return;
  const phase = snapshot.run?.phase ?? "unknown";
  text("controller-run-state", snapshot.run?.state_label || titleCase(phase));
  elements["controller-study"].hidden = !snapshot.browser_study;
  if (snapshot.browser_study) text("controller-study", snapshot.browser_study.title);
  text("controller-progress", snapshot.run?.progress_label, "No progress reported.");
  text("controller-event", snapshot.run?.event_label, "No current event.");
  const elapsed = Number(snapshot.active_block?.elapsed_s) || 0;
  const duration = Number(snapshot.active_block?.duration_s) || 0;
  elements["controller-progress-bar"].style.width = `${duration > 0 ? Math.min(100, elapsed / duration * 100) : 0}%`;
  renderTrialTimeline("controller", snapshot.browser_trial, snapshot.browser_trials ?? []);
  updateControllerActions();
}

function trialMarkers(trial) {
  const response = trial.response_required ? trial.rt_ms + " ms RT" : trial.rt_ms + " ms · catch tap";
  return [
    ["Audio scheduled", trial.audio_ms, "audio"],
    ["Vibration requested", trial.tactile_ms, "tactile"],
    ["Response · " + response, trial.response_ms, "response"],
  ].filter(([, offset]) => offset !== null).sort((a, b) => a[1] - b[1]);
}

function renderTrialTimeline(role, trial, recent) {
  const panel = elements[`${role}-timeline`];
  panel.hidden = !trial;
  if (!trial) return;
  text(`${role}-trial-number`, "Trial " + trial.number + (trial.response_required ? "" : " · Withhold"));
  const track = elements[`${role}-timeline-track`];
  const list = elements[`${role}-timeline-list`];
  track.replaceChildren();
  list.replaceChildren();
  for (const [label, offset, kind] of trialMarkers(trial)) {
    const mark = document.createElement("span");
    mark.dataset.cue = kind;
    mark.style.left = (100 * offset / trial.duration_ms) + "%";
    track.append(mark);
    const item = document.createElement("li");
    item.textContent = "+" + offset + " ms · " + label;
    list.append(item);
  }
  elements[`${role}-recent-trials`].hidden = recent.length === 0;
  const history = elements[`${role}-recent-trial-list`];
  history.replaceChildren();
  for (const entry of recent) {
    const item = document.createElement("li");
    const markers = trialMarkers(entry).map(([label, offset]) => "+" + offset + " ms " + label);
    item.textContent = ["Trial " + entry.number, ...markers].join(" · ");
    history.append(item);
  }
}

function updateControllerActions() {
  const status = controllerSession?.status();
  const ready = browserActive && status?.controlReady === true;
  const busy = status?.reliableCommandBusy === true;
  const granted = new Set(status?.grantedScopes || []);
  const allowed = new Set(status?.snapshot?.allowed_actions || []);
  document.querySelectorAll("[data-remote-action]").forEach((button) => {
    const action = button.dataset.remoteAction;
    const scope = requiredScope(action);
    button.disabled = !(ready && !busy && scope && granted.has(scope) && allowed.has(action));
  });
  text("controller-scopes", status?.grantedScopes?.length ? status.grantedScopes.join(", ") : "None");
  text("controller-pending", status?.pendingCommands ?? 0);
  elements["controller-session-panel"].hidden = !ready;
  elements["controller-role"].disabled = Boolean(status && !["idle", "closed", "error", "disconnected"].includes(status.phase));
  let next = controllerInvitation ? "Invitation ready. Open Remote control and press Connect." : "Open Remote control to scan for a runner, or open an invitation.";
  if (!browserActive) next = "Control suspended while this page is hidden or offline.";
  else if (status?.phase === "ready" && !ready) next = "Authenticated. Waiting for fresh target state…";
  else if (ready) {
    const current = status.snapshot;
    next = !granted.has(SCOPES.TRANSPORT) ? "Observe only. State comes from the target."
      : busy ? "Command sent. Waiting for the target's acknowledgement…"
        : !current.setup?.ready ? "Complete participant setup on the device running the experiment."
          : !current.safety?.local_armed ? "Arm outputs on the device running the experiment."
            : current.run?.phase === "running" ? "Running. Pause or stop when needed."
              : current.run?.phase === "paused" ? "Paused. Review the target, then resume when ready."
                : "Ready. Choose an available run action.";
  } else if (["connecting", "authenticating"].includes(status?.phase)) next = "Connecting to the target…";
  else if (["closed", "error", "disconnected"].includes(status?.phase)) next = "Connection lost. Press Connect to fetch fresh target state.";
  text("controller-next-step", next);
  if (ready) setConnectionStatus("ready", granted.has(SCOPES.TRANSPORT) ? "Controls ready" : "Observe only");
}

function bindControllerSession(session) {
  const on = (type, handler) => session.addEventListener(type, (event) => {
    if (controllerSession === session) handler(event);
  });
  on("phasechange", (event) => {
    setConnectionStatus(event.detail.phase, titleCase(event.detail.phase));
    elements["controller-connect"].disabled = !browserActive || !["idle", "closed", "error", "disconnected"].includes(event.detail.phase);
    elements["controller-stop"].disabled = ["idle", "closed"].includes(event.detail.phase);
    updateControllerActions();
  });
  on("ready", (event) => {
    text("controller-scopes", event.detail.grantedScopes.join(", "));
    showToast("Pairing verified. Waiting for fresh target state.");
    updateControllerActions();
  });
  on("snapshot", (event) => renderControllerSnapshot(event.detail.snapshot));
  on("pendingchange", updateControllerActions);
  on("commandunknown", (event) => {
    elements["controller-outcome"].hidden = false;
    text("controller-outcome", `${titleCase(event.detail.action)} outcome unknown. Reconnect and check the target before issuing another action. No command was retried.`);
    updateControllerActions();
  });
  on("commandapplied", (event) => {
    const accepted = event.detail.status !== "rejected";
    showToast(`${event.detail.action}: ${event.detail.reason}`, { error: !accepted });
    updateControllerActions();
  });
  on("protocolerror", (event) => { showToast(event.detail.message, { error: true }); updateControllerActions(); });
  on("remoteerror", (event) => showToast(event.detail.message, { error: true }));
  on("relaypeer", (event) => {
    const message = event.detail.message || "Relay peer state changed.";
    showToast(message);
  });
  on("transportstatus", (event) => {
    if (event.detail?.message) text("controller-transport", `VDO data-only · ${event.detail.message}`);
  });
  on("quality", (event) => {
    const route = event.detail?.route || "unknown";
    const rtt = Number.isFinite(event.detail?.rttMs) ? ` · ${event.detail.rttMs} ms RTT` : "";
    text("controller-transport", `VDO data-only · ${route}${rtt}`);
  });
}

function vdoTransport({ role, room, secret, targetId }) {
  return new PpsVdoTransport({
    role,
    room,
    sharedSecret: secret,
    label: role === "target" ? `PPS phone target ${targetId.slice(-8)}` : "PPS browser controller",
  });
}

function requestedControllerScopes() {
  if (elements["controller-role"].value === "observer") return [SCOPES.READ];
  return [...DEFAULT_REMOTE_SCOPES, SCOPES.ANNOTATE, SCOPES.ABORT].sort();
}

function availablePhoneScopes() {
  const scopes = [...DEFAULT_REMOTE_SCOPES];
  if (elements["target-allow-notes"].checked) scopes.push(SCOPES.ANNOTATE);
  if (elements["target-allow-abort"].checked) scopes.push(SCOPES.ABORT);
  return [...new Set(scopes)].sort();
}

function renderBeaconTargets(targets = []) {
  const list = elements["beacon-targets"];
  list.replaceChildren();
  if (targets.length === 0) {
    const empty = document.createElement("p");
    empty.className = "subtle";
    empty.textContent = "No public PPS targets are currently visible.";
    list.append(empty);
    return;
  }
  for (const target of targets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "beacon-target-button";
    button.dataset.streamId = target.streamId;
    const name = document.createElement("strong");
    name.textContent = target.label;
    const identifier = document.createElement("span");
    identifier.textContent = `Beacon code · ${target.streamId.slice(-12)}`;
    button.append(name, identifier);
    button.addEventListener("click", async () => {
      try {
        list.querySelectorAll("button").forEach((candidate) => { candidate.disabled = true; });
        await controllerBeacon?.selectTarget(target.streamId);
      } catch (error) {
        list.querySelectorAll("button").forEach((candidate) => { candidate.disabled = false; });
        showToast(error.message, { error: true });
      }
    });
    list.append(button);
  }
}

async function stopControllerBeacon() {
  const beacon = controllerBeacon;
  controllerBeacon = null;
  controllerBeaconRequestId = "";
  elements["beacon-request"].disabled = true;
  elements["beacon-stop"].disabled = true;
  elements["beacon-browse"].disabled = false;
  renderBeaconTargets();
  text("beacon-selection", "Match the beacon code shown on the target before requesting access.");
  if (beacon) await beacon.stop();
  text("beacon-status", "Beacon off");
}

function bindControllerBeacon(beacon) {
  beacon.addEventListener("status", (event) => {
    text("beacon-status", event.detail.error ? "Beacon error" : titleCase(event.detail.phase));
    elements["beacon-status"].dataset.tone = event.detail.error ? "danger" : "";
  });
  beacon.addEventListener("targetschange", (event) => renderBeaconTargets(event.detail.targets));
  beacon.addEventListener("targetselected", (event) => {
    text("beacon-selection", `${event.detail.label} selected. Waiting for its private-request channel.`);
  });
  beacon.addEventListener("peeropen", () => {
    elements["beacon-request"].disabled = false;
    text("beacon-selection", "Public request channel ready. The target still has to approve locally.");
  });
  beacon.addEventListener("peerclose", () => {
    elements["beacon-request"].disabled = true;
    text("beacon-selection", "The selected public target left. Stop and browse again.");
  });
  beacon.addEventListener("pairingrequested", (event) => {
    controllerBeaconRequestId = event.detail.requestId;
    elements["beacon-request"].disabled = true;
    text("beacon-selection", "Private access requested. Waiting for target-local approval.");
  });
  beacon.addEventListener("pairingoffer", (event) => {
    if (event.detail.requestId !== controllerBeaconRequestId) return;
    const offer = beacon.takePrivateOffer(event.detail.requestId);
    controllerBeaconRequestId = "";
    if (!offer) {
      showToast("The approved private offer expired before it could be accepted.", { error: true });
      return;
    }
    controllerInvitation = {
      mode: "controller",
      transport: "vdo",
      targetId: offer.targetId,
      sessionId: offer.sessionId,
      room: offer.room,
      secret: offer.secret,
      requestedScopes: offer.acceptedScopes,
      expiresUnixMs: offer.expiresUnixMs,
    };
    text("invite-badge", "Private offer loaded");
    elements["invite-badge"].dataset.tone = "ready";
    text("invite-summary", "Target approval received. Press Connect to perform mutual BRSP proof in the fresh private room.");
    text("controller-target", offer.targetId);
    text("controller-transport", "VDO data-only (private, not connected)");
    elements["controller-connect"].disabled = false;
    text("beacon-selection", "Private offer loaded. Public discovery can now stop safely.");
    void stopControllerBeacon();
    showToast("Target approved a private session. Press Connect to authenticate.");
  });
  beacon.addEventListener("pairingrejected", (event) => {
    controllerBeaconRequestId = "";
    text("beacon-selection", `Request not approved: ${titleCase(event.detail.reason)}.`);
    showToast("The public target did not approve private access.", { error: true });
  });
  beacon.addEventListener("protocolerror", (event) => showToast(event.detail.message, { error: true }));
}

function renderPendingTargetRequest() {
  const requests = targetBeacon?.pendingPairingRequests() ?? [];
  pendingTargetRequest = requests[0] ?? null;
  updateRemoteAttention(elements["remote-attention"], pendingTargetRequest, phoneTarget?.session?.phase === "ready");
  elements["target-pairing-request"].hidden = !pendingTargetRequest;
  if (!pendingTargetRequest) return;
  text("target-request-label", pendingTargetRequest.label, "Browser controller");
  text("target-request-scopes", pendingTargetRequest.requestedScopes.join(", "), "no scopes");
}

async function stopTargetBeacon() {
  const beacon = targetBeacon;
  targetBeacon = null;
  clearTimeout(targetBeaconExpiry);
  targetBeaconExpiry = null;
  elements["target-beacon-code"].hidden = true;
  renderPendingTargetRequest();
  elements["target-beacon-stop"].disabled = true;
  elements["target-beacon-start"].disabled = false;
  if (beacon) await beacon.stop();
  text("target-beacon-status", "Beacon off");
}

function bindTargetBeacon(beacon) {
  beacon.addEventListener("status", (event) => {
    if (targetBeacon !== beacon) return;
    text("target-beacon-status", event.detail.error ? "Beacon error" : titleCase(event.detail.phase));
    const advertising = event.detail.phase === "advertising" && !event.detail.error;
    elements["target-beacon-code"].hidden = !advertising;
    if (advertising) text("target-beacon-code", "Beacon code: " + event.detail.streamId.slice(-12));
    elements["target-beacon-status"].dataset.tone = event.detail.error ? "danger" : "";
  });
  beacon.addEventListener("pairingrequest", () => {
    renderPendingTargetRequest();
    showToast("A public controller requests private access. Review it before approving.");
  });
  beacon.addEventListener("pairingcancelled", renderPendingTargetRequest);
  beacon.addEventListener("pairingrejected", renderPendingTargetRequest);
  beacon.addEventListener("protocolerror", (event) => showToast(event.detail.message, { error: true }));
}

function initializeInvitation() {
  try {
    controllerInvitation = parseInvitation(location.href);
    stripInvitationMaterial();
    if (!controllerInvitation) return;
    activateMode("controller");
    text("invite-badge", "Invite loaded");
    elements["invite-badge"].dataset.tone = "ready";
    const transportLabel = controllerInvitation.transport === "vdo"
      ? "the private data-only WebRTC room"
      : controllerInvitation.transport === "relay"
        ? "the room relay"
        : "the desktop target";
    text("invite-summary", `Invitation loaded for ${controllerInvitation.targetId}. Press Connect to open ${transportLabel}.`);
    text("controller-target", controllerInvitation.targetId);
    text("controller-transport", controllerInvitation.transport === "vdo"
      ? "VDO data-only (not connected)"
      : controllerInvitation.transport === "relay"
        ? `Relay room ${controllerInvitation.room}`
        : "Desktop LAN target");
    elements["controller-connect"].disabled = false;
  } catch (error) {
    stripInvitationMaterial();
    text("invite-badge", "Invalid invite");
    elements["invite-badge"].dataset.tone = "danger";
    showToast(error.message, { error: true });
  }
}

function connectController() {
    if (!controllerInvitation) return;
    try {
      if (!browserActive) throw new Error("Return to this page while online before connecting.");
      if (controllerInvitation.expiresUnixMs && controllerInvitation.expiresUnixMs <= Date.now()) {
        controllerInvitation = null;
        elements["controller-connect"].disabled = true;
        text("invite-badge", "Offer expired");
        throw new Error("The approved private offer expired. Scan for the beacon and request access again.");
      }
      controllerSession?.stop();
      const transport = controllerInvitation.transport === "vdo"
        ? vdoTransport({
          role: "controller",
          room: controllerInvitation.room,
          secret: controllerInvitation.secret,
          targetId: controllerInvitation.targetId,
        })
        : undefined;
      controllerSession = new BrspControllerSession({
        url: transport ? undefined : webSocketUrl({
          locationUrl: location.href,
          transport: controllerInvitation.transport,
          room: controllerInvitation.room,
          role: "controller",
        }),
        transport,
        secret: controllerInvitation.secret,
        targetId: controllerInvitation.targetId,
        sessionId: controllerInvitation.sessionId,
        requestedScopes: elements["controller-role"].value === "observer"
          ? controllerInvitation.requestedScopes.filter((scope) => scope === SCOPES.READ)
          : controllerInvitation.requestedScopes,
      });
      bindControllerSession(controllerSession);
      controllerSession.connect();
    } catch (error) { showToast(error.message, { error: true }); }
}

function bindControllerControls() {
  elements["controller-connect"].addEventListener("click", connectController);
  elements["controller-stop"].addEventListener("click", () => {
    resumeController = false;
    controllerSession?.stop();
  });
  elements["controller-role"].addEventListener("change", updateControllerActions);

  document.querySelectorAll("[data-remote-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.remoteAction;
      let args = {};
      if (action === "session.note") {
        args = { text: elements["remote-note"].value };
      } else if (action === "part.start") {
        args = { part_number: controllerSession.snapshot?.part?.selected_part ?? controllerSession.snapshot?.part?.available_parts?.[0] ?? 1 };
      } else if (action === "instruction.continue") {
        args = { gate_id: controllerSession.snapshot?.instruction_gate?.gate_id ?? "" };
      }
      if (action === "run.abort" && !confirm("Abort the remote target run?")) return;
      try {
        controllerSession.sendCommand(action, args);
        updateControllerActions();
      } catch (error) { showToast(error.message, { error: true }); }
    });
  });
}

function appendEvent(event, source) {
  eventLog.push({
    sequence: ++eventSequence,
    source,
    browser_monotonic_ms: performance.now(),
    ...event,
  });
  if (eventLog.length > 2_000) eventLog = eventLog.slice(-2_000);
  elements["download-phone-log"].disabled = eventLog.length === 0;
}

function publishPhoneSnapshot() {
  if (phoneTarget?.session.phase === "ready") phoneTarget.session.publishState(publicRunnerSnapshot(phoneSnapshot));
}

function updateStudyStep(label, gate) {
  responseWindow.close();
  trialStartMs = null;
  phoneSnapshot = browserStudyStep(phoneSnapshot, label, clock, gate);
  renderPhoneSnapshot();
  publishPhoneSnapshot();
}

function recordTrialMarker(patch, action, source) {
  const trial = phoneSnapshot.browser_trial;
  if (!trial || trialStartMs === null) return;
  const durationMs = Math.max(trial.duration_ms, patch.tactile_ms ?? 0, patch.response_ms ?? 0);
  phoneSnapshot = recordBrowserTrial(phoneSnapshot, { ...trial, ...patch, duration_ms: durationMs }, clock);
  appendEvent({ action, revision: phoneSnapshot.revision, ...patch }, source);
  publishPhoneSnapshot();
}

function applyEffects(effects) {
  for (const effect of effects) {
    if (effect.type === "study.start") {
      const study = loadedStudy;
      setTimeout(() => {
        if (study && loadedStudy === study && phoneSnapshot.run.phase === "running") void studyPlayback.start(study);
      }, 0);
    } else if (effect.type === "study.continue") {
      studyPlayback.continue();
    } else if (effect.type === "demo.start") {
      try {
        const { startAt, useTactile } = outputEngine.startDemo();
        trialStartMs = startAt;
        responseWindow.close();
        if (!useTactile && outputEngine.audioEnabled) responseWindow.open(startAt);
        phoneSnapshot = recordBrowserTrial(phoneSnapshot, {
          number: (phoneSnapshot.browser_trial?.number ?? 0) + 1,
          response_required: true,
          duration_ms: useTactile ? DEMO_DURATION_MS : DEMO_AUDIO_MS,
          audio_ms: outputEngine.audioEnabled ? 0 : null,
          tactile_ms: null,
          response_ms: null,
          rt_ms: null,
        }, clock, { advanceRevision: false });
      } catch (error) {
        reportOutputError(error);
      }
    } else if (["demo.pause", "demo.stop"].includes(effect.type)) {
      studyPlayback.stop();
      outputEngine.stopDemo();
      trialStartMs = null;
      responseWindow.close();
    } else if (effect.type === "outputs.stop") {
      studyPlayback.stop();
      outputEngine.disarm();
      trialStartMs = null;
      responseWindow.close();
    }
  }
}

function renderPhoneSnapshot() {
  if (!phoneSnapshot) return;
  const phase = phoneSnapshot.run.phase;
  text("phone-run-state", phoneSnapshot.run.state_label || titleCase(phase));
  text("phone-event", phoneSnapshot.run.event_label);
  text("phone-study-summary", phoneSnapshot.browser_study?.title, "Practice demo");
  text("phone-readiness", !phoneSnapshot.setup.ready ? "Complete participant setup."
    : !phoneSnapshot.package_verified ? "Prepare the selected study."
      : !phoneSnapshot.safety.local_armed ? "Open Outputs and arm this device."
        : "Device outputs armed.");
  renderTrialTimeline("phone", phoneSnapshot.browser_trial, phoneSnapshot.browser_trials ?? []);
  const allowed = new Set(phoneSnapshot.allowed_actions);
  elements["phone-setup"].disabled = !allowed.has("setup.submit");
  elements["phone-study"].disabled = phoneSnapshot.run.thread_alive || studyLoading;
  elements["phone-prepare"].disabled = phoneSnapshot.run.thread_alive || studyLoading;
  elements["phone-start"].disabled = !allowed.has("part.start");
  elements["phone-pause"].disabled = !allowed.has("run.pause");
  elements["phone-resume"].disabled = !allowed.has("run.resume");
  elements["phone-stop"].disabled = !allowed.has("run.stop");
  const participant = elements["phone-participant-view"];
  const gate = phase === "instruction_gate" && Boolean(phoneSnapshot.browser_study);
  const showing = phase === "running" || gate;
  const continueButton = elements["participant-continue"];
  const continueHadFocus = document.activeElement === continueButton;
  const showContinue = gate && continueButton.hidden;
  continueButton.hidden = !gate;
  if (showing) {
    const instruction = gate ? phoneSnapshot.instruction_gate.instruction_label : outputEngine.vibrationEnabled
      ? "Tap when you feel the vibration."
      : "Tap when you hear the sound.";
    text("phone-response-instruction", instruction);
    if (gate) text("participant-continue", phoneSnapshot.instruction_gate.button_label || "Continue");
  }
  if (participant.hidden === showing) {
    if (showing) document.querySelector(".runner-dialog[open]")?.close();
    participant.hidden = !showing;
    document.querySelector(".app-shell").inert = showing;
    document.querySelector(".skip-link").inert = showing;
    if (showing) {
      (gate ? continueButton : elements["participant-stop"]).focus({ preventScroll: true });
    } else {
      responseWindow.contacts.clear();
      elements["phone-run-state"].focus({ preventScroll: true });
    }
  }
  if (showing && showContinue) continueButton.focus({ preventScroll: true });
  if (showing && !gate && continueHadFocus) elements["participant-stop"].focus({ preventScroll: true });
  const capabilities = outputEngine.capabilities();
  elements["phone-audio-enabled"].disabled = !capabilities.audio || armPending || phoneSnapshot.safety.local_armed;
  elements["phone-vibration-enabled"].disabled = !capabilities.vibration || armPending || phoneSnapshot.safety.local_armed;
  elements["arm-phone"].disabled = !browserActive || armPending || studyLoading || !allowed.has("target.arm");
  elements["disarm-phone"].disabled = !allowed.has("target.disarm");
  text("target-state-badge", phoneTarget?.session?.phase === "ready" ? "Remote ready" : titleCase(phoneSnapshot.connection_state));
  elements["target-state-badge"].dataset.tone = phoneTarget?.session?.phase === "ready" ? "ready" : "";
  updateRemoteAttention(elements["remote-attention"], pendingTargetRequest, phoneTarget?.session?.phase === "ready");
}

function applyPhone(action, args = {}, { source = "local", expectedRevision = null, publish = true } = {}) {
  if (!phoneSnapshot) throw new Error("The browser experiment is not ready.");
  const outcome = applyPhoneAction(phoneSnapshot, action, args, { clock, expectedRevision });
  phoneSnapshot = outcome.snapshot;
  appendEvent(outcome.event, source);
  if (outcome.status === "accepted") applyEffects(outcome.effects);
  renderPhoneSnapshot();
  if (publish && phoneTarget?.session?.phase === "ready") phoneTarget.session.publishState(publicRunnerSnapshot(phoneSnapshot));
  return { ...outcome, snapshot: phoneSnapshot };
}

function targetCommandOutcome(command) {
  const outcome = applyPhone(command.action, command.args, {
    source: `controller:${phoneTarget.session.controller?.id || "authenticated"}`,
    expectedRevision: command.expected_revision,
    publish: false,
  });
  return outcome;
}

function expirePhoneControllerLease() {
  if (!phoneSnapshot) return;
  if (phoneSnapshot.browser_study && phoneSnapshot.run.thread_alive) {
    applyPhone("target.disarm", {}, { source: "controller-disconnected", publish: false });
    return;
  }
  const outcome = expirePhoneLease(phoneSnapshot, { clock });
  phoneSnapshot = outcome.snapshot;
  appendEvent(outcome.event, "target");
  applyEffects(outcome.effects);
  renderPhoneSnapshot();
}

function bindTargetSession(session) {
  const on = (type, handler) => session.addEventListener(type, (event) => {
    if (phoneTarget?.session === session) handler(event);
  });
  on("phasechange", (event) => {
    setConnectionStatus(event.detail.phase, event.detail.message);
    if (phoneSnapshot) {
      phoneSnapshot = setPhoneConnectionMetadata(phoneSnapshot, {
        connectionState: event.detail.phase,
        controllerId: session.controller?.id || "",
        leaseExpiresAtUnixMs: null,
        clock,
      });
      renderPhoneSnapshot();
    }
    elements["target-connect"].disabled = !["idle", "closed", "error"].includes(event.detail.phase);
    elements["target-disconnect"].disabled = ["idle", "closed"].includes(event.detail.phase);
    elements["target-disconnect"].hidden = elements["target-disconnect"].disabled;
  });
  on("ready", () => {
    if (phoneTarget?.session === session && phoneTarget.offerExpiresUnixMs
      && Date.now() >= phoneTarget.offerExpiresUnixMs) {
      if (phoneTarget.offerTimer) clearTimeout(phoneTarget.offerTimer);
      phoneTarget.offerTimer = null;
      session.stop();
      showToast("The approved private offer expired before authentication completed.", { error: true });
      return;
    }
    if (phoneTarget?.session === session && phoneTarget.offerTimer) {
      clearTimeout(phoneTarget.offerTimer);
      phoneTarget.offerTimer = null;
    }
    phoneSnapshot = setPhoneConnectionMetadata(phoneSnapshot, {
      connectionState: "ready",
      controllerId: session.controller?.id || "",
      leaseExpiresAtUnixMs: Date.now() + session.status().leaseRemainingMs,
      clock,
    });
    renderPhoneSnapshot();
    session.publishState(publicRunnerSnapshot(phoneSnapshot));
    appendEvent({ action: "remote.ready", revision: phoneSnapshot.revision, unix_ms: Date.now() }, "target");
    showToast("Controller authenticated. Local phone target remains authoritative.");
  });
  on("leaserenewed", (event) => {
    if (!phoneSnapshot) return;
    phoneSnapshot = setPhoneConnectionMetadata(phoneSnapshot, {
      connectionState: "ready",
      controllerId: event.detail.controllerId || session.controller?.id || "",
      leaseExpiresAtUnixMs: Date.now() + event.detail.leaseRemainingMs,
      clock,
    });
    renderPhoneSnapshot();
  });
  on("leaseexpired", (event) => {
    showToast(event.detail.reason === "controller_lease_expired"
      ? "Controller heartbeat expired. The phone target paused and revoked remote authority."
      : "Controller disconnected. The phone target revoked remote authority.");
  });
  on("protocolerror", (event) => showToast(event.detail.message, { error: true }));
  on("remoteerror", (event) => showToast(event.detail.message, { error: true }));
  on("relaypeer", (event) => showToast(event.detail.message || "Relay peer state changed."));
}

async function createPhoneTarget({ pairing = null, autoConnect = false } = {}) {
  if (phoneSnapshot.run.thread_alive) throw new Error("Stop the local run before creating a new connection.");
  if (phoneTarget?.offerTimer) clearTimeout(phoneTarget.offerTimer);
  phoneTarget?.session.stop();
  outputEngine.disarm();
  const room = pairing?.room ?? generateVdoRoomId();
  const targetId = pairing?.targetId ?? createProtocolIdentity("phone_target");
  const sessionId = pairing?.sessionId ?? room;
  const epoch = createProtocolEpoch();
  const secret = pairing?.secret ?? createPairingSecret();
  const availableScopes = pairing?.acceptedScopes ?? availablePhoneScopes();
  const actions = Object.keys(ACTION_SCOPE);
  phoneSnapshot = createPhoneExperimentSnapshot({ targetId, epoch, clock });
  if (loadedStudy) phoneSnapshot = prepareBrowserStudy(phoneSnapshot, loadedStudy, clock);
  eventLog = [];
  eventSequence = 0;
  targetInvitationUrl = pairing ? "" : createVdoInvitation({
    pageUrl: location.href,
    room,
    targetId,
    secret,
    scopes: availableScopes,
  });
  phoneTarget = {
    room,
    targetId,
    secret,
    availableScopes,
    actions,
    offerExpiresUnixMs: pairing?.expiresUnixMs ?? null,
    offerTimer: null,
    session: new BrspTargetSession({
      transport: vdoTransport({ role: "target", room, secret, targetId }),
      secret,
      targetId,
      sessionId,
      epoch,
      availableScopes,
      actions,
      getSnapshot: () => publicRunnerSnapshot(phoneSnapshot),
      applyCommand: targetCommandOutcome,
      onLeaseExpired: expirePhoneControllerLease,
    }),
  };
  bindTargetSession(phoneTarget.session);
  if (pairing?.expiresUnixMs) {
    const ownedTarget = phoneTarget;
    ownedTarget.offerTimer = setTimeout(() => {
      if (phoneTarget !== ownedTarget || ownedTarget.session.phase === "ready") return;
      ownedTarget.session.stop();
      ownedTarget.offerTimer = null;
      showToast("The approved private offer expired before a controller authenticated.", { error: true });
    }, Math.max(0, pairing.expiresUnixMs - Date.now()));
  }
  elements["target-room"].value = room;
  elements["target-pairing"].hidden = Boolean(pairing);
  if (!pairing) await renderQrCode(elements["target-qr"], targetInvitationUrl);
  text("target-state-badge", "Target created");
  elements["target-connect"].disabled = false;
  renderPhoneSnapshot();
  appendEvent({ action: "target.created", revision: 0, unix_ms: Date.now() }, "local");
  if (autoConnect) {
    await Promise.resolve(phoneTarget.session.connect());
    showToast("Approved private target started. The controller must still connect and prove its secret.");
  } else {
    showToast("Private target created locally. VDO signaling remains disconnected until you press Start private data target.");
  }
}

function bindPublicBeaconControls() {
  elements["beacon-browse"].addEventListener("click", async () => {
    try {
      await stopControllerBeacon();
      const beacon = new PpsPublicBeacon({ role: "controller", label: "PPS website controller" });
      controllerBeacon = beacon;
      bindControllerBeacon(beacon);
      elements["beacon-browse"].disabled = true;
      elements["beacon-stop"].disabled = false;
      await beacon.startBrowsing();
    } catch (error) {
      showToast(error.message, { error: true });
      if (controllerBeacon) await stopControllerBeacon();
    }
  });
  elements["beacon-stop"].addEventListener("click", () => {
    void stopControllerBeacon().catch((error) => showToast(error.message, { error: true }));
  });
  elements["beacon-request"].addEventListener("click", () => {
    try {
      controllerBeacon?.requestPairing({ requestedScopes: requestedControllerScopes() });
    } catch (error) { showToast(error.message, { error: true }); }
  });

  elements["target-beacon-start"].addEventListener("click", async () => {
    try {
      await stopTargetBeacon();
      const beacon = new PpsPublicBeacon({ role: "target", label: "PPS browser runner" });
      targetBeacon = beacon;
      bindTargetBeacon(beacon);
      elements["target-beacon-start"].disabled = true;
      elements["target-beacon-stop"].disabled = false;
      await beacon.startAdvertising();
      if (targetBeacon === beacon) {
        targetBeaconExpiry = setTimeout(() => {
          void stopTargetBeacon().catch((error) => showToast(error.message, { error: true }));
          showToast("Beacon expired. Send a new beacon when ready.");
        }, 120_000);
      }
    } catch (error) {
      showToast(error.message, { error: true });
      if (targetBeacon) await stopTargetBeacon();
    }
  });
  elements["target-beacon-stop"].addEventListener("click", () => {
    void stopTargetBeacon().catch((error) => showToast(error.message, { error: true }));
  });
  elements["target-request-deny"].addEventListener("click", () => {
    if (!pendingTargetRequest || !targetBeacon) return;
    targetBeacon.rejectPairing(pendingTargetRequest.requestId);
    renderPendingTargetRequest();
    showToast("Private access request denied.");
  });
  elements["target-request-approve"].addEventListener("click", async () => {
    if (!pendingTargetRequest || !targetBeacon) return;
    if (phoneSnapshot.run.thread_alive) {
      showToast("Stop the local run before allowing a new controller.", { error: true });
      return;
    }
    const request = pendingTargetRequest;
    const allowed = new Set(availablePhoneScopes());
    const acceptedScopes = request.requestedScopes.filter((scope) => allowed.has(scope)).sort();
    try {
      const offer = targetBeacon.approvePairing(request.requestId, {
        targetId: createProtocolIdentity("phone_target"),
        acceptedScopes,
        expiresUnixMs: Date.now() + 90_000,
      });
      pendingTargetRequest = null;
      elements["target-pairing-request"].hidden = true;
      await createPhoneTarget({ pairing: offer, autoConnect: true });
      await stopTargetBeacon();
    } catch (error) {
      showToast(error.message, { error: true });
      renderPendingTargetRequest();
    }
  });
}

async function prepareSelectedStudy() {
  const id = elements["phone-study"].value;
  if (!id) {
    if (loadedStudy) {
      loadedStudy = null;
      outputEngine.disarm();
      phoneSnapshot = prepareBrowserStudy(phoneSnapshot, null, clock);
    }
    applyPhone("package.prepare_demo");
    return;
  }
  studyLoading = true;
  renderPhoneSnapshot();
  try {
    const study = await loadPhoneStudy(studyBase, id);
    if (phoneSnapshot.run.thread_alive) throw new Error("Stop the active run before changing studies.");
    if (!outputEngine.capabilities().audio || (study.needsVibration && !outputEngine.capabilities().vibration)) {
      throw new Error("This study needs audio and phone vibration. Open it in Chrome on Android.");
    }
    outputEngine.disarm();
    loadedStudy = study;
    studyPlayback.results = [];
    phoneSnapshot = prepareBrowserStudy(phoneSnapshot, study, clock);
    appendEvent({ action: "study.prepared", profile_id: id }, "local");
    publishPhoneSnapshot();
    showToast("Study prepared. Submit setup, then arm outputs.");
  } finally {
    studyLoading = false;
    renderPhoneSnapshot();
  }
}

function bindPhoneTargetControls() {
  const capabilities = outputEngine.capabilities();
  for (const [id, supported] of [["phone-audio-enabled", capabilities.audio], ["phone-vibration-enabled", capabilities.vibration]]) {
    elements[id].checked = supported;
    elements[id].disabled = !supported;
  }
  text("output-capability", `${capabilities.audio ? "Audio" : "No audio"} • ${capabilities.vibration ? "Vibration API" : "No vibration API"}`);
  elements["create-phone-target"].addEventListener("click", () => void createPhoneTarget().catch((error) => showToast(error.message, { error: true })));
  elements["copy-target-invite"].addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(targetInvitationUrl);
      showToast("Controller invitation copied.");
    } catch { showToast("Clipboard access was denied.", { error: true }); }
  });
  elements["target-connect"].addEventListener("click", () => {
    try { phoneTarget?.session.connect(); } catch (error) { showToast(error.message, { error: true }); }
  });
  elements["target-disconnect"].addEventListener("click", () => phoneTarget?.session.stop());

  elements["arm-phone"].addEventListener("click", async () => {
    if (armPending || studyLoading || !phoneSnapshot.allowed_actions.includes("target.arm")) return;
    armPending = true;
    const study = loadedStudy;
    const target = phoneTarget;
    const participantCode = phoneSnapshot.setup.participant_code;
    renderPhoneSnapshot();
    try {
      const audioEnabled = elements["phone-audio-enabled"].checked;
      const vibrationEnabled = elements["phone-vibration-enabled"].checked;
      if (study && (!audioEnabled || (study.needsVibration && !vibrationEnabled))) {
        throw new Error("Enable this study’s audio and vibration outputs.");
      }
      await outputEngine.arm({ audioEnabled, vibrationEnabled });
      if (!browserActive || studyLoading || study !== loadedStudy || target !== phoneTarget ||
          participantCode !== phoneSnapshot.setup.participant_code ||
          !phoneSnapshot.allowed_actions.includes("target.arm")) {
        outputEngine.disarm();
        return;
      }
      applyPhone("target.arm", { audio_enabled: audioEnabled }, { source: "local-gesture" });
      showToast(vibrationEnabled ? "Outputs armed. Check that you felt the test pulse." : "Audio armed.");
    } catch (error) {
      outputEngine.disarm();
      showToast(error.message, { error: true });
    } finally {
      armPending = false;
      renderPhoneSnapshot();
    }
  });
  elements["disarm-phone"].addEventListener("click", () => applyPhone("target.disarm", {}, { source: "local-gesture" }));
  elements["phone-setup"].addEventListener("click", () => applyPhone("setup.submit", {
    participant_code: elements["phone-participant-code"].value,
    participant_name: "",
    name_sharing_opt_in: false,
    age: null,
    handedness: "unspecified",
    gender: "unspecified",
    part_labels: { "1": "Phone demo", "2": "Phone demo" },
  }));
  elements["phone-prepare"].addEventListener("click", () => {
    void prepareSelectedStudy().catch((error) => showToast(error.message, { error: true }));
  });
  elements["phone-study"].addEventListener("change", () => {
    if (loadedStudy || phoneSnapshot.package_verified) {
      outputEngine.disarm();
      loadedStudy = null;
      phoneSnapshot = prepareBrowserStudy(phoneSnapshot, null, clock);
      publishPhoneSnapshot();
    }
    text("phone-prepare", elements["phone-study"].value ? "Prepare study" : "Prepare demo");
    renderPhoneSnapshot();
  });
  void phoneStudyCatalog(studyBase).then((catalogue) => {
    for (const study of catalogue) elements["phone-study"].add(new Option(study.title, study.id));
  }).catch(() => {
    text("phone-catalogue-status", "Study catalogue unavailable. Reload to try again or use the practice demo.");
    elements["phone-catalogue-status"].hidden = false;
  });
  elements["phone-start"].addEventListener("click", () => applyPhone("part.start"));
  elements["phone-pause"].addEventListener("click", () => applyPhone("run.pause"));
  elements["phone-resume"].addEventListener("click", () => applyPhone("run.resume"));
  elements["phone-stop"].addEventListener("click", () => applyPhone("run.stop"));
  elements["participant-continue"].addEventListener("click", () => {
    applyPhone("instruction.continue", { gate_id: phoneSnapshot.instruction_gate.gate_id }, { source: "local-participant" });
  });
  elements["participant-stop"].addEventListener("click", () => applyPhone("run.stop", {}, { source: "local-participant" }));
  const surface = elements["phone-response"];
  surface.addEventListener("pointerdown", (event) => {
    if (!event.isTrusted || event.button !== 0 || phoneSnapshot?.run.phase !== "running") return;
    surface.setPointerCapture(event.pointerId);
    responseWindow.down(event);
  });
  surface.addEventListener("pointermove", (event) => responseWindow.move(event));
  surface.addEventListener("pointercancel", (event) => responseWindow.cancel(event));
  surface.addEventListener("lostpointercapture", (event) => responseWindow.cancel(event));
  surface.addEventListener("contextmenu", (event) => event.preventDefault());
  surface.addEventListener("pointerup", (event) => {
    if (!event.isTrusted || trialStartMs === null) return;
    const response = responseWindow.up(event);
    if (!response) return;
    if (response.trialNumber !== undefined) {
      const record = studyPlayback.results[response.trialNumber - 1];
      record.response_ms = Math.round(response.atMs - record.trial_start_ms);
      record.rt_ms = Math.round(response.reactionTimeMs);
      const { trial_start_ms, response_anchor_ms, vibration_lateness_ms, ...publicTrial } = record;
      phoneSnapshot = recordBrowserTrial(phoneSnapshot, publicTrial, clock);
      appendEvent({ action: "response.tap", ...publicTrial }, "local-participant");
      publishPhoneSnapshot();
    } else {
      recordTrialMarker({
        response_ms: Math.round(response.atMs - trialStartMs),
        rt_ms: Math.round(response.reactionTimeMs),
      }, "response.tap", "local-participant");
    }
  });
  outputEngine.addEventListener("output-error", (event) => reportOutputError(event.detail));
  outputEngine.addEventListener("vibration-requested", (event) => {
    if (trialStartMs === null || phoneSnapshot?.run.phase !== "running") return;
    const { atMs } = event.detail;
    responseWindow.open(atMs);
    recordTrialMarker({ tactile_ms: Math.round(atMs - trialStartMs) }, "tactile.requested", "browser-output");
  });
  outputEngine.addEventListener("complete", (event) => {
    if (phoneSnapshot?.run.phase === "running") {
      const outcome = applyPhone("run.complete_demo", {}, { source: "browser-output" });
      appendEvent({ action: "timing.observed", ...event.detail, revision: outcome.snapshot.revision }, "browser-output");
    }
  });
  elements["download-phone-log"].addEventListener("click", () => {
    const artifact = {
      schema: "pps-browser-phone-experiment-log.v1",
      timing_tier: "browser_exploratory",
      warning: "Browser audio and vibration timing is exploratory and is not publication-qualified.",
      exported_at: new Date().toISOString(),
      target_id: phoneSnapshot?.target_id,
      final_snapshot: phoneSnapshot,
      trials: loadedStudy ? studyPlayback.results.filter(Boolean) : [],
      earlier_events: eventSequence - eventLog.length,
      events: eventLog,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(artifact, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `pps-phone-experiment-${Date.now()}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  });
}

function isEmbeddedContext() {
  try {
    return window.top !== window.self;
  } catch {
    return true;
  }
}

function blockEmbeddedContext() {
  stripInvitationMaterial();
  elements["embedding-warning"].hidden = false;
  setConnectionStatus("blocked", "Open directly");
  document.querySelectorAll("button, input, select, textarea").forEach((control) => {
    control.disabled = true;
  });
}

function start() {
  if (isEmbeddedContext()) {
    blockEmbeddedContext();
    return;
  }
  bindRunnerControls();
  bindModeSwitch();
  initializeInvitation();
  bindControllerControls();
  bindPublicBeaconControls();
  bindPhoneTargetControls();
  phoneSnapshot = createPhoneExperimentSnapshot({
    targetId: createProtocolIdentity("phone_target"), epoch: createProtocolEpoch(), clock,
  });
  renderPhoneSnapshot();
  updateControllerActions();
  setConnectionStatus("idle", "Not connected");
  installBrowserLifecycle({
    suspend: () => {
      browserActive = false;
      clearTimeout(toastTimer);
      elements["companion-toast"].classList.remove("is-visible");
      resumeController = Boolean(controllerSession && ["connecting", "authenticating", "ready"].includes(controllerSession.phase));
      controllerSession?.stop();
      if (phoneTarget?.offerTimer) clearTimeout(phoneTarget.offerTimer);
      phoneTarget?.session.stop();
      if (phoneSnapshot) applyPhone("target.disarm", {}, { source: "browser-suspended" });
      outputEngine.disarm();
      void stopControllerBeacon();
      void stopTargetBeacon();
      elements["controller-connect"].disabled = true;
      setConnectionStatus("suspended", "Suspended");
      updateControllerActions();
    },
    resume: () => {
      browserActive = true;
      const reconnect = resumeController;
      resumeController = false;
      elements["controller-connect"].disabled = !controllerInvitation;
      setConnectionStatus("idle", "Reconnecting");
      updateControllerActions();
      // One transport attempt. No experiment action or phone output is replayed.
      if (reconnect) connectController();
      else setConnectionStatus("idle", "Not connected");
      renderPhoneSnapshot();
    },
  });
}

start();
