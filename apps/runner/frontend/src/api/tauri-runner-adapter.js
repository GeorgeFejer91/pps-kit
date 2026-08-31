import { invoke } from "@tauri-apps/api/core";

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

export function createTauriRunnerAdapter({ invokeFn = invoke } = {}) {
  if (typeof invokeFn !== "function") throw new TypeError("A Tauri invoke function is required.");
  return Object.freeze({
    kind: "tauri-native",
    snapshot() {
      return call(invokeFn, "runner_snapshot");
    },
    dispatch(action, args = {}) {
      return call(invokeFn, "runner_dispatch", { action, args });
    },
    selectPreparedSession() {
      return call(invokeFn, "select_prepared_session");
    },
    inspectPreparedExecution() {
      return call(invokeFn, "inspect_prepared_execution");
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
