import {
  ACTION_SCOPE,
  DEFAULT_REMOTE_SCOPES,
  SCOPES,
  requiredScope,
} from "./domain/runner-contract.js";
import {
  allowedPhoneActions,
  applyPhoneAction,
  createPhoneExperimentSnapshot,
  expirePhoneLease,
  setPhoneConnectionMetadata,
} from "./domain/phone-experiment-reducer.js";
import { BrowserOutputEngine } from "./phone/browser-output-engine.js";
import { createRelayInvitation, parseInvitation, stripInvitationMaterial, webSocketUrl } from "./remote/invitation.js";
import { createPairingSecret, createProtocolEpoch, createProtocolIdentity } from "./remote/protocol.js";
import { BrspControllerSession, BrspTargetSession } from "./remote/websocket-session.js";
import { renderQrCode } from "./ui/qr-code.js";

const elements = Object.fromEntries([...document.querySelectorAll("[id]")].map((element) => [element.id, element]));
const outputEngine = new BrowserOutputEngine();
let controllerInvitation = null;
let controllerSession = null;
let phoneTarget = null;
let phoneSnapshot = null;
let targetInvitationUrl = "";
let eventLog = [];
let toastTimer = null;

function clock() {
  return {
    unixMs: Date.now(),
    monotonicNs: Math.floor(performance.now() * 1_000_000),
  };
}

function text(id, value, fallback = "—") {
  if (elements[id]) elements[id].textContent = value === undefined || value === null || value === "" ? fallback : String(value);
}

function titleCase(value) {
  return String(value || "unknown").replaceAll("_", " ").replace(/\b\w/gu, (letter) => letter.toUpperCase());
}

function showToast(message, { error = false } = {}) {
  clearTimeout(toastTimer);
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
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-mode-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.modePanel === mode));
}

function bindModeSwitch() {
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => activateMode(button.dataset.mode)));
}

function renderControllerSnapshot(snapshot) {
  if (!snapshot) return;
  const phase = snapshot.run?.phase ?? "unknown";
  text("controller-run-state", snapshot.run?.state_label || titleCase(phase));
  text("controller-revision", `rev ${snapshot.revision ?? 0}`);
  text("controller-progress", snapshot.run?.progress_label, "No progress reported.");
  text("controller-event", snapshot.run?.event_label, "No current event.");
  const elapsed = Number(snapshot.active_block?.elapsed_s) || 0;
  const duration = Number(snapshot.active_block?.duration_s) || 0;
  elements["controller-progress-bar"].style.width = `${duration > 0 ? Math.min(100, elapsed / duration * 100) : 0}%`;
  updateControllerActions();
}

function updateControllerActions() {
  const status = controllerSession?.status();
  const ready = status?.phase === "ready";
  const granted = new Set(status?.grantedScopes || []);
  const allowed = new Set(status?.snapshot?.allowed_actions || []);
  document.querySelectorAll("[data-remote-action]").forEach((button) => {
    const action = button.dataset.remoteAction;
    const scope = requiredScope(action);
    button.disabled = !(ready && scope && granted.has(scope) && allowed.has(action));
  });
  text("controller-scopes", status?.grantedScopes?.length ? status.grantedScopes.join(", ") : "None");
  text("controller-pending", status?.pendingCommands ?? 0);
}

function bindControllerSession(session) {
  session.addEventListener("phasechange", (event) => {
    setConnectionStatus(event.detail.phase, event.detail.message);
    elements["controller-connect"].disabled = !["idle", "closed", "error"].includes(event.detail.phase);
    elements["controller-stop"].disabled = ["idle", "closed"].includes(event.detail.phase);
    updateControllerActions();
  });
  session.addEventListener("ready", (event) => {
    text("controller-scopes", event.detail.grantedScopes.join(", "));
    showToast("Mutual proof verified. Controls reflect target-returned state.");
    updateControllerActions();
  });
  session.addEventListener("snapshot", (event) => renderControllerSnapshot(event.detail.snapshot));
  session.addEventListener("pendingchange", updateControllerActions);
  session.addEventListener("commandapplied", (event) => {
    const accepted = event.detail.status !== "rejected";
    showToast(`${event.detail.action}: ${event.detail.reason}`, { error: !accepted });
    updateControllerActions();
  });
  session.addEventListener("protocolerror", (event) => showToast(event.detail.message, { error: true }));
  session.addEventListener("remoteerror", (event) => showToast(event.detail.message, { error: true }));
  session.addEventListener("relaypeer", (event) => {
    const message = event.detail.message || "Relay peer state changed.";
    showToast(message);
  });
}

function initializeInvitation() {
  try {
    controllerInvitation = parseInvitation(location.href);
    stripInvitationMaterial();
    if (!controllerInvitation) return;
    activateMode("controller");
    text("invite-badge", "Invite loaded");
    elements["invite-badge"].dataset.tone = "ready";
    text("invite-summary", `Invitation loaded for ${controllerInvitation.targetId}. Press Connect to open ${controllerInvitation.transport === "relay" ? "the room relay" : "the desktop target"}.`);
    text("controller-target", controllerInvitation.targetId);
    text("controller-transport", controllerInvitation.transport === "relay" ? `Relay room ${controllerInvitation.room}` : "Desktop LAN target");
    elements["controller-connect"].disabled = false;
  } catch (error) {
    stripInvitationMaterial();
    text("invite-badge", "Invalid invite");
    elements["invite-badge"].dataset.tone = "danger";
    showToast(error.message, { error: true });
  }
}

function bindControllerControls() {
  elements["controller-connect"].addEventListener("click", () => {
    if (!controllerInvitation) return;
    try {
      controllerSession?.stop();
      controllerSession = new BrspControllerSession({
        url: webSocketUrl({
          locationUrl: location.href,
          transport: controllerInvitation.transport,
          room: controllerInvitation.room,
          role: "controller",
        }),
        secret: controllerInvitation.secret,
        targetId: controllerInvitation.targetId,
        sessionId: controllerInvitation.sessionId,
        requestedScopes: controllerInvitation.requestedScopes,
      });
      bindControllerSession(controllerSession);
      controllerSession.connect();
    } catch (error) { showToast(error.message, { error: true }); }
  });
  elements["controller-stop"].addEventListener("click", () => controllerSession?.stop());

  document.querySelectorAll("[data-remote-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.remoteAction;
      let args = {};
      if (action === "setup.submit") {
        args = {
          participant_code: elements["remote-participant-code"].value,
          participant_name: "",
          name_sharing_opt_in: false,
          age: Number(elements["remote-participant-age"].value),
          handedness: elements["remote-participant-handedness"].value,
          gender: elements["remote-participant-gender"].value,
          part_labels: controllerSession.snapshot?.setup?.part_labels ?? { "1": "Part 1", "2": "Part 2" },
        };
      } else if (action === "session.note") {
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
    sequence: eventLog.length + 1,
    source,
    browser_monotonic_ms: performance.now(),
    ...event,
  });
  if (eventLog.length > 2_000) eventLog = eventLog.slice(-2_000);
  elements["download-phone-log"].disabled = eventLog.length === 0;
}

function applyEffects(effects) {
  for (const effect of effects) {
    if (effect.type === "demo.start") {
      try {
        outputEngine.startDemo();
        elements["looming-orbit"].classList.remove("is-running");
        requestAnimationFrame(() => elements["looming-orbit"].classList.add("is-running"));
      } catch (error) {
        showToast(error.message, { error: true });
      }
    } else if (["demo.pause", "demo.stop"].includes(effect.type)) {
      outputEngine.stopDemo();
      elements["looming-orbit"].classList.remove("is-running");
    } else if (effect.type === "outputs.stop") {
      outputEngine.disarm();
      elements["looming-orbit"].classList.remove("is-running");
    }
  }
}

function renderPhoneSnapshot() {
  if (!phoneSnapshot) return;
  const phase = phoneSnapshot.run.phase;
  text("phone-run-state", phoneSnapshot.run.state_label || titleCase(phase));
  text("phone-revision", `rev ${phoneSnapshot.revision}`);
  text("phone-event", phoneSnapshot.run.event_label);
  const allowed = new Set(phoneSnapshot.allowed_actions);
  elements["phone-setup"].disabled = !allowed.has("setup.submit");
  elements["phone-prepare"].disabled = !allowed.has("package.prepare_demo");
  elements["phone-start"].disabled = !allowed.has("part.start");
  elements["phone-pause"].disabled = !allowed.has("run.pause");
  elements["phone-resume"].disabled = !allowed.has("run.resume");
  elements["phone-stop"].disabled = !allowed.has("run.stop");
  elements["arm-phone"].disabled = !allowed.has("target.arm");
  elements["disarm-phone"].disabled = !allowed.has("target.disarm");
  text("target-state-badge", phoneTarget?.session?.phase === "ready" ? "Remote ready" : titleCase(phoneSnapshot.connection_state));
  elements["target-state-badge"].dataset.tone = phoneTarget?.session?.phase === "ready" ? "ready" : "";
}

function applyPhone(action, args = {}, { source = "local", expectedRevision = null, publish = true } = {}) {
  if (!phoneSnapshot) throw new Error("Create the phone target first.");
  const outcome = applyPhoneAction(phoneSnapshot, action, args, { clock, expectedRevision });
  phoneSnapshot = outcome.snapshot;
  appendEvent(outcome.event, source);
  if (outcome.status === "accepted") applyEffects(outcome.effects);
  renderPhoneSnapshot();
  if (publish && phoneTarget?.session?.phase === "ready") phoneTarget.session.publishState(phoneSnapshot);
  return outcome;
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
  const outcome = expirePhoneLease(phoneSnapshot, { clock });
  phoneSnapshot = outcome.snapshot;
  appendEvent(outcome.event, "target");
  applyEffects(outcome.effects);
  renderPhoneSnapshot();
}

function bindTargetSession(session) {
  session.addEventListener("phasechange", (event) => {
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
  });
  session.addEventListener("ready", () => {
    phoneSnapshot = setPhoneConnectionMetadata(phoneSnapshot, {
      connectionState: "ready",
      controllerId: session.controller?.id || "",
      leaseExpiresAtUnixMs: Date.now() + session.status().leaseRemainingMs,
      clock,
    });
    renderPhoneSnapshot();
    session.publishState(phoneSnapshot);
    appendEvent({ action: "remote.ready", revision: phoneSnapshot.revision, unix_ms: Date.now() }, "target");
    showToast("Controller authenticated. Local phone target remains authoritative.");
  });
  session.addEventListener("leaserenewed", (event) => {
    if (!phoneSnapshot) return;
    phoneSnapshot = setPhoneConnectionMetadata(phoneSnapshot, {
      connectionState: "ready",
      controllerId: event.detail.controllerId || session.controller?.id || "",
      leaseExpiresAtUnixMs: Date.now() + event.detail.leaseRemainingMs,
      clock,
    });
    renderPhoneSnapshot();
  });
  session.addEventListener("leaseexpired", (event) => {
    showToast(event.detail.reason === "controller_lease_expired"
      ? "Controller heartbeat expired. The phone target paused and revoked remote authority."
      : "Controller disconnected. The phone target revoked remote authority.");
  });
  session.addEventListener("protocolerror", (event) => showToast(event.detail.message, { error: true }));
  session.addEventListener("remoteerror", (event) => showToast(event.detail.message, { error: true }));
  session.addEventListener("relaypeer", (event) => showToast(event.detail.message || "Relay peer state changed."));
}

async function createPhoneTarget() {
  phoneTarget?.session.stop();
  outputEngine.disarm();
  const room = elements["target-room"].value.trim() || createProtocolIdentity("room");
  const targetId = createProtocolIdentity("phone_target");
  const epoch = createProtocolEpoch();
  const secret = createPairingSecret();
  const availableScopes = [...DEFAULT_REMOTE_SCOPES];
  if (elements["target-allow-notes"].checked) availableScopes.push(SCOPES.ANNOTATE);
  if (elements["target-allow-abort"].checked) availableScopes.push(SCOPES.ABORT);
  const actions = Object.keys(ACTION_SCOPE);
  phoneSnapshot = createPhoneExperimentSnapshot({ targetId, epoch, clock });
  eventLog = [];
  targetInvitationUrl = createRelayInvitation({
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
    session: new BrspTargetSession({
      url: webSocketUrl({ locationUrl: location.href, transport: "relay", room, role: "target" }),
      secret,
      targetId,
      sessionId: room,
      epoch,
      availableScopes,
      actions,
      getSnapshot: () => phoneSnapshot,
      applyCommand: targetCommandOutcome,
      onLeaseExpired: expirePhoneControllerLease,
    }),
  };
  bindTargetSession(phoneTarget.session);
  elements["target-room"].value = room;
  elements["target-pairing"].hidden = false;
  await renderQrCode(elements["target-qr"], targetInvitationUrl);
  text("target-state-badge", "Target created");
  elements["target-connect"].disabled = false;
  renderPhoneSnapshot();
  appendEvent({ action: "target.created", revision: 0, unix_ms: Date.now() }, "local");
  showToast("Target created locally. Relay remains disconnected until you press Connect target.");
}

function bindPhoneTargetControls() {
  const capabilities = outputEngine.capabilities();
  text("output-capability", `${capabilities.audio ? "Audio" : "No audio"} • ${capabilities.vibration ? "Vibration" : "No vibration"}`);
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
    try {
      await outputEngine.arm({
        audioEnabled: elements["phone-audio-enabled"].checked,
        vibrationEnabled: elements["phone-vibration-enabled"].checked,
      });
      applyPhone("target.arm", { audio_enabled: elements["phone-audio-enabled"].checked }, { source: "local-gesture" });
      showToast("Phone outputs armed by local gesture.");
    } catch (error) { showToast(error.message, { error: true }); }
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
  elements["phone-prepare"].addEventListener("click", () => applyPhone("package.prepare_demo"));
  elements["phone-start"].addEventListener("click", () => applyPhone("part.start"));
  elements["phone-pause"].addEventListener("click", () => applyPhone("run.pause"));
  elements["phone-resume"].addEventListener("click", () => applyPhone("run.resume"));
  elements["phone-stop"].addEventListener("click", () => applyPhone("run.stop"));
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

function start() {
  bindModeSwitch();
  initializeInvitation();
  bindControllerControls();
  bindPhoneTargetControls();
  updateControllerActions();
  setConnectionStatus("idle", "Not connected");
  addEventListener("pagehide", () => {
    controllerSession?.stop();
    phoneTarget?.session.stop();
    outputEngine.disarm();
  }, { once: true });
}

start();
