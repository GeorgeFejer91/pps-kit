import { applyPhoneAction, createPhoneExperimentSnapshot } from "../domain/phone-experiment-reducer.js";

function clone(value) {
  return structuredClone(value);
}

function previewClock() {
  let tick = 0;
  return () => ({
    unixMs: 1_700_000_000_000 + tick,
    monotonicNs: 1_000_000_000 + tick++,
  });
}

export function createPreviewRunnerAdapter() {
  const clock = previewClock();
  let sequence = 0;
  let snapshot = createPhoneExperimentSnapshot({
    targetId: "pps-browser-preview",
    epoch: 1,
    clock,
  });
  snapshot.target_kind = "desktop-browser-preview";
  snapshot.timing_tier = "desktop_preview";
  snapshot.connection_state = "browser_preview_local_only";
  snapshot.package_label = "No deterministic preview prepared";
  snapshot.setup.part_labels = { "1": "Preview Part 1", "2": "Preview Part 2" };
  snapshot.setup.part_label_options = ["Preview Part 1", "Preview Part 2"];
  snapshot.part.available_parts = [1, 2];

  const remoteStatus = () => ({
    enabled: false,
    allowAbort: false,
    bindAddress: "Not available in browser preview",
    baseUrl: "",
    controllerUrl: "",
    targetId: snapshot.target_id,
    sessionId: "",
    epoch: snapshot.epoch,
    controllerConnected: false,
    controllerId: null,
    grantedScopes: [],
    serverAvailable: false,
    serverError: null,
    transport: "disabled-in-browser-preview",
    productionTransportQualified: false,
    message: "Browser preview is local-only. Launch the Tauri app to enable authenticated LAN control.",
  });
  const nativeAuthorityUnavailable = () => {
    throw new Error("Native remote authority is unavailable in ordinary-browser preview mode.");
  };

  return Object.freeze({
    kind: "browser-preview",
    async snapshot() {
      return clone(snapshot);
    },
    async dispatch(action, args = {}) {
      const outcome = applyPhoneAction(snapshot, action, args, { clock });
      snapshot = outcome.snapshot;
      sequence += 1;
      return {
        id: `preview-${String(sequence).padStart(6, "0")}`,
        action,
        status: outcome.status,
        reason: outcome.reason,
        accepted_revision: outcome.acceptedRevision,
        resulting_revision: outcome.resultingRevision,
        snapshot: clone(snapshot),
      };
    },
    async selectPreparedSession() {
      throw new Error("Prepared-session selection is available only in the native Tauri runner.");
    },
    async remoteStatus() {
      return remoteStatus();
    },
    async configureRemote({ enabled }) {
      if (enabled) throw new Error("Remote networking is disabled in ordinary-browser preview mode.");
      return remoteStatus();
    },
    async rotatePairing() {
      throw new Error("Pairing exists only in the native Tauri runner.");
    },
    async remoteSessionClaim() {
      return nativeAuthorityUnavailable();
    },
    async remoteSessionRenew() {
      return nativeAuthorityUnavailable();
    },
    async remoteSessionDispatch() {
      return nativeAuthorityUnavailable();
    },
    async remoteSessionRevoke() {
      return nativeAuthorityUnavailable();
    },
  });
}
