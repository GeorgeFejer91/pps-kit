import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

function messageFromError(error) {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && typeof error.message === "string") return error.message;
  return "The native runner rejected the request.";
}

async function call(invokeFn, command, args) {
  try {
    return await invokeFn(command, args);
  } catch (error) {
    const wrapped = new Error(messageFromError(error), { cause: error });
    if (error && typeof error === "object" && typeof error.code === "string") wrapped.code = error.code;
    throw wrapped;
  }
}

export function createTauriRunnerAdapter({ invokeFn = invoke, listenFn = listen } = {}) {
  if (typeof invokeFn !== "function") throw new TypeError("A Tauri invoke function is required.");
  return Object.freeze({
    kind: "tauri-native",
    snapshot() {
      return call(invokeFn, "runner_snapshot");
    },
    subscribeSnapshots(handler) {
      return listenFn("runner-snapshot", (event) => handler(event.payload), {
        target: { kind: "WebviewWindow", label: "main" },
      });
    },
    dispatch(action, args = {}) {
      return call(invokeFn, "runner_dispatch", { action, args });
    },
    selectPreparedSession() {
      return call(invokeFn, "select_prepared_session");
    },
    prepareExperimentProfile() {
      return call(invokeFn, "prepare_experiment_profile");
    },
    inspectPreparedExecution() {
      return call(invokeFn, "inspect_prepared_execution");
    },
    prepareCurrentAudioBlock() {
      return call(invokeFn, "prepare_current_audio_block");
    },
    nativeOutputStatus() {
      return call(invokeFn, "native_output_status");
    },
    enumerateNativeOutput() {
      return call(invokeFn, "native_output_enumerate");
    },
    reserveNativeOutput({ policyGeneration, serviceGeneration, inventoryGeneration,
      deviceOrdinal, configOrdinal, channels, sampleRateHz }) {
      return call(invokeFn, "native_output_reserve_silence", { request: {
        policyGeneration, serviceGeneration, inventoryGeneration,
        deviceOrdinal, configOrdinal, channels, sampleRateHz,
        bufferFrames: null, warmupTimeoutMs: 3000,
      } });
    },
    releaseNativeOutput({ policyGeneration, serviceGeneration, reservationGeneration }) {
      return call(invokeFn, "native_output_release", { request: {
        policyGeneration, serviceGeneration, reservationGeneration,
      } });
    },
    disableNativeOutput() {
      return call(invokeFn, "native_output_disable");
    },
    activateNativeExecution({ policyGeneration, serviceGeneration, reservationGeneration,
      acknowledgeUnqualified }) {
      return call(invokeFn, "activate_native_execution", { request: {
        reservation: { policyGeneration, serviceGeneration, reservationGeneration },
        acknowledgeUnqualified: acknowledgeUnqualified === true,
      } });
    },
    recordResponse({ choice = "", x = null, y = null } = {}) {
      return call(invokeFn, "runner_record_response", { request: { choice, x, y } });
    },
    remoteStatus() {
      return call(invokeFn, "remote_status");
    },
    configureRemote({ enabled, allowAbort, lanListener = true }) {
      return call(invokeFn, "configure_remote", {
        enabled: Boolean(enabled),
        allowAbort: Boolean(allowAbort),
        lanListener: Boolean(lanListener),
      });
    },
    rotatePairing() {
      return call(invokeFn, "rotate_pairing");
    },
    remoteSessionClaim({ sessionId, controllerId, acceptedScopes, readySequence }) {
      return call(invokeFn, "remote_session_claim", {
        request: { sessionId, controllerId, acceptedScopes: [...acceptedScopes], readySequence },
      });
    },
    remoteSessionRenew({ sessionId, ownerToken, controlSequence }) {
      return call(invokeFn, "remote_session_renew", {
        request: { sessionId, ownerToken, controlSequence },
      });
    },
    remoteSessionDispatch({ sessionId, ownerToken, controlSequence, command }) {
      return call(invokeFn, "remote_session_dispatch", {
        request: { sessionId, ownerToken, controlSequence, command },
      });
    },
    remoteSessionRevoke({ sessionId, ownerToken }) {
      return call(invokeFn, "remote_session_revoke", {
        request: { sessionId, ownerToken },
      });
    },
  });
}
