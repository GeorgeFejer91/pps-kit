// Serialized by Playwright into the page: keep this function closure-free.
// This observes the pinned Tauri Windows fetch transport, never its invoke key.
export function installNativeExternalLinkTrace() {
  "use strict";
  const descriptor = Object.getOwnPropertyDescriptor(window, "fetch");
  if (!descriptor?.writable || typeof descriptor.value !== "function") {
    throw new Error("Native IPC fetch observation requires a writable fetch value");
  }
  const original = descriptor.value;
  const receipts = [];
  const observer = async function (...args) {
    let receipt;
    try {
      const [input, options] = args;
      const address = new URL(typeof input === "string" ? input : input?.url ?? input?.href, window.location.href);
      if (address.href === "http://ipc.localhost/designer_open_external") {
        const method = String(options?.method ?? input?.method ?? "GET").toUpperCase();
        if (method === "POST") {
          receipt = { url: null, method, pending: true };
          receipts.push(receipt);
          // Tauri's Windows transport sends a JSON string in options.body.
          // Unknown request shapes remain real fetches, but cannot prove a URL.
          const payload = JSON.parse(options?.body);
          if (typeof payload?.url !== "string") throw new Error("Unobservable IPC URL");
          receipt.url = payload.url;
        }
      }
    } catch {
      if (receipt) receipt.observationFailed = true;
    }

    let response;
    try {
      response = await Reflect.apply(original, this, args);
    } catch (error) {
      if (receipt) {
        receipt.pending = false;
        receipt.transportFailed = true;
      }
      throw error;
    }
    if (receipt) {
      try {
        receipt.reply = response.headers.get("Tauri-Response");
        receipt.opened = await response.clone().json();
      } catch {
        // Observability must never reject the real response: Tauri would then
        // retry over postMessage and could open the external link a second time.
        receipt.observationFailed = true;
      }
      receipt.pending = false;
    }
    return response;
  };
  Object.defineProperty(window, "fetch", { ...descriptor, value: observer });
  if (window.fetch !== observer) {
    Object.defineProperty(window, "fetch", descriptor);
    throw new Error("Native IPC fetch observation was not installed");
  }
  window.externalLinkReceipts = receipts;
  window.restoreExternalLinkTrace = () => Object.defineProperty(window, "fetch", descriptor);
}
