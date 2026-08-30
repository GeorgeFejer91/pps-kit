import { createPreviewRunnerAdapter } from "./preview-runner-adapter.js";
import { createTauriRunnerAdapter } from "./tauri-runner-adapter.js";

export function selectRunnerAdapter(globalObject = globalThis) {
  const nativeBridge = globalObject?.__TAURI_INTERNALS__;
  if (nativeBridge && typeof nativeBridge.invoke === "function") return createTauriRunnerAdapter();
  return createPreviewRunnerAdapter();
}
