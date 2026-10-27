import { convertFileSrc, invoke, isTauri } from "@tauri-apps/api/core";

// Deliberate native adapter. A native failure is surfaced; it never retries HTTP/Python.
export function createNativeDesigner(call = invoke, enabled = typeof window !== "undefined" && isTauri()) {
  let revision = 0;
  let capabilities = null;
  let epoch = 0;
  let queue = Promise.resolve();
  let activeJob = null;
  let pendingJob = false;
  let invalidationPending = false;
  const enqueue = operation => {
    const next = queue.then(operation);
    queue = next.catch(() => {});
    return next;
  };
  const status = message => document.dispatchEvent(new CustomEvent("pps-native-status", { detail: message }));
  return {
    enabled,
    get capabilities() { return capabilities; },
    resourceUrl: path => convertFileSrc(String(path).replace(/^\/+/, ""), "pps-resource"),
    async load() {
      return enqueue(async () => {
        const response = await call("designer_snapshot");
        revision = response.revision;
        capabilities = response.capabilities || null;
        return response;
      });
    },
    invalidate() {
      if (!enabled) return;
      epoch++;
      if (invalidationPending) return;
      invalidationPending = true;
      enqueue(async () => {
        try { revision = await call("designer_invalidate", { expectedRevision: revision }); }
        finally { invalidationPending = false; }
      }).catch(error => status(`Native synchronization failed: ${error.message || error}`));
    },
    async save(snapshot) {
      const captured = structuredClone(snapshot);
      return enqueue(async () => { revision = await call("designer_save", { expectedRevision: revision, snapshot: captured }); });
    },
    pickAudio: () => enqueue(() => call("designer_pick_audio")),
    async exportProfile(blob) {
      if (blob.size > 270 * 1024 * 1024) throw new Error("Portable profile exceeds the native export limit.");
      return call("designer_export_profile", new Uint8Array(await blob.arrayBuffer()));
    },
    async importProfile() {
      epoch++;
      return enqueue(async () => {
        const result = await call("designer_import_profile", { expectedRevision: revision });
        if (result) revision = result.revision;
        return result;
      });
    },
    async generate(snapshot, payload, optIn) {
      return this.runJob("designer_generate", { snapshot: structuredClone(snapshot), payload, optIn }, "Generating native audio…");
    },
    async baseline(snapshot, source, optIn) {
      return this.runJob("designer_baseline", { snapshot: structuredClone(snapshot), source, optIn }, "Generating a stationary control…");
    },
    async review(snapshot, variants) {
      return this.runJob("designer_review", { snapshot: structuredClone(snapshot), variants }, "Verifying full blocks and participant order…");
    },
    async accept(hashes) {
      await enqueue(() => call("designer_accept_review", { expectedRevision: revision, hashes }));
      return this.load();
    },
    async prepare(participant, identity) {
      return this.runJob("designer_prepare", { participant, identity }, "Preparing immutable participant files…");
    },
    openPrepared: () => call("designer_open_prepared"),
    exportAudio: reference => call("designer_export_audio", { reference }),
    async runJob(command, args, message) {
      if (pendingJob || activeJob) throw new Error("Native work is already running.");
      const origin = epoch;
      pendingJob = true;
      try {
        const job = await enqueue(() => call(command, { expectedRevision: revision, ...args }));
        if (!job) return null;
        activeJob = job.job_id;
        status(message);
        for (;;) {
          await new Promise(done => setTimeout(done, 250));
          const current = await call("designer_job", { jobId: job.job_id });
          if (!["succeeded", "failed", "cancelled"].includes(current.status)) continue;
          if (current.status !== "succeeded") throw new Error(current.result?.error || current.message || current.status);
          const response = await this.load();
          if (origin !== epoch) throw new Error("The draft changed. Obsolete generation was discarded.");
          status(current.message || "Native work complete.");
          return { snapshot: response.snapshot, result: current.result };
        }
      } finally { activeJob = null; pendingJob = false; }
    },
    async cancel() {
      epoch++;
      if (activeJob || pendingJob) { await enqueue(() => call("designer_cancel")); status("Cancelling native work…"); }
    },
  };
}

export const nativeDesigner = createNativeDesigner();
