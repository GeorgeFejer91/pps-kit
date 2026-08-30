import { selectRunnerAdapter } from "./api/runner-api.js";
import { renderQrCode } from "./ui/qr-code.js";

const api = selectRunnerAdapter();
const elements = Object.fromEntries([...document.querySelectorAll("[id]")].map((element) => [element.id, element]));
let snapshot = null;
let remoteStatus = null;
let invitationUrl = "";
let toastTimer = null;

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
}

function readRemoteUrl(status) {
  return status?.controllerUrl ?? status?.controller_url ?? status?.invitation_url ?? status?.invite_url ?? status?.pairing_url ?? status?.invitationUrl ?? "";
}

async function renderRemote(next) {
  if (!next || typeof next !== "object") return;
  remoteStatus = next;
  const enabled = Boolean(next.enabled);
  const serverAvailable = Boolean(next.server_available ?? next.serverAvailable);
  const serverError = next.server_error ?? next.serverError ?? "";
  const connected = Boolean(next.controller_connected ?? next.controllerConnected);
  elements["remote-enabled"].checked = enabled;
  elements["remote-allow-abort"].checked = Boolean(next.allow_abort ?? next.allowAbort);
  text("remote-state-badge", connected ? "Controller ready" : enabled && !serverAvailable ? "Unavailable" : enabled ? "Waiting" : "Disabled");
  elements["remote-state-badge"].dataset.tone = connected ? "ready" : "";
  text(
    "remote-detail",
    serverError || next.status_message || next.message,
    enabled
      ? serverAvailable
        ? "Remote target enabled; waiting for explicit controller connection."
        : "Remote target is enabled but the LAN companion server is unavailable."
      : serverAvailable
        ? "Remote control is disabled; the previously opted-in companion listener remains fail-closed until app exit."
        : "Remote networking is inert until explicitly enabled.",
  );
  text("remote-controller", next.controller_id ?? next.controllerId, "None");
  const scopes = next.granted_scopes ?? next.grantedScopes ?? [];
  text("remote-scopes", Array.isArray(scopes) && scopes.length ? scopes.join(", ") : "None");
  text("remote-route", next.transport ?? next.route_label ?? next.bindAddress ?? next.bind_address ?? "Local Wi-Fi WebSocket");

  invitationUrl = readRemoteUrl(next);
  await renderQrCode(elements["pairing-qr"], invitationUrl);
  elements["pairing-placeholder"].hidden = Boolean(invitationUrl);
  elements["copy-invite"].disabled = !invitationUrl;
  text("pairing-summary", invitationUrl
    ? `Fresh invitation for ${next.target_id ?? next.targetId ?? "this runner"}. The secret remains in the fragment.`
    : "The secret is held in the URL fragment and is not sent in an HTTP request.");
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
  const status = result?.status;
  if (status === "rejected") throw new Error(result.reason || `${action} was rejected.`);
  showToast(`${action} applied by the native target.`);
  return result;
}

function argsForAction(action) {
  if (action === "part.start") {
    return { part_number: snapshot?.part?.selected_part ?? snapshot?.part?.available_parts?.[0] ?? 1 };
  }
  if (action === "instruction.continue") {
    return { gate_id: snapshot?.instruction_gate?.gate_id ?? "" };
  }
  return {};
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

function bindActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      if (action === "run.abort" && !confirm("Abort the active run? This is logged as an interruption.")) return;
      button.disabled = true;
      try { await dispatch(action, argsForAction(action)); } catch (error) { showToast(error.message, { error: true }); }
      finally { if (snapshot) renderSnapshot(snapshot); }
    });
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

  elements["remote-apply"].addEventListener("click", async () => {
    try {
      await renderRemote(await api.configureRemote({
        enabled: elements["remote-enabled"].checked,
        allowAbort: elements["remote-allow-abort"].checked,
      }));
      showToast(elements["remote-enabled"].checked ? "Phone remote enabled." : "Phone remote disabled and active producers stopped.");
    } catch (error) { showToast(error.message, { error: true }); }
  });

  elements["rotate-pairing"].addEventListener("click", async () => {
    try {
      await renderRemote(await api.rotatePairing());
      showToast("Pairing material rotated; older invitations are invalid.");
    } catch (error) { showToast(error.message, { error: true }); }
  });

  elements["copy-invite"].addEventListener("click", async () => {
    if (!invitationUrl) return;
    try {
      await navigator.clipboard.writeText(invitationUrl);
      showToast("Invitation copied. Treat it as a short-lived secret.");
    } catch { showToast("Clipboard access was denied by the system.", { error: true }); }
  });
}

async function start() {
  bindTabs();
  bindActions();
  try {
    const [initialSnapshot, initialRemote] = await Promise.all([api.snapshot(), api.remoteStatus()]);
    renderSnapshot(normalizedSnapshot(initialSnapshot));
    await renderRemote(initialRemote);
  } catch (error) {
    text("state-chip", "Native bridge unavailable");
    showToast(error.message, { error: true });
  }

  setInterval(() => {
    if (document.visibilityState !== "visible") return;
    void Promise.all([refreshSnapshot(), refreshRemote()]).catch(() => {});
  }, 1_000);
}

void start();
