import { invoke } from "@tauri-apps/api/core";

function messageFromError(error) {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && typeof error.message === "string") return error.message;
  return "The native runner rejected the request.";
}

async function call(command, args) {
  try {
    return await invoke(command, args);
  } catch (error) {
    throw new Error(messageFromError(error), { cause: error });
  }
}

export function createTauriRunnerAdapter() {
  return Object.freeze({
    kind: "tauri-native",
    snapshot() {
      return call("runner_snapshot");
    },
    dispatch(action, args = {}) {
      return call("runner_dispatch", { action, args });
    },
    remoteStatus() {
      return call("remote_status");
    },
    configureRemote({ enabled, allowAbort }) {
      return call("configure_remote", { enabled: Boolean(enabled), allowAbort: Boolean(allowAbort) });
    },
    rotatePairing() {
      return call("rotate_pairing");
    },
  });
}
