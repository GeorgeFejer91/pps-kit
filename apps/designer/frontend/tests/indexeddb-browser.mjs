import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";

export async function verifyAbortedBrowserWrites(page, evidencePath) {
  const evidence = await page.evaluate(async () => {
    const drafts = window.PPSDesigner.drafts;
    const originalState = window.PPSDesignerApp.getState();
    const previous = structuredClone(originalState);
    const attempted = structuredClone(originalState);
    attempted.design.name = "Aborted draft must not replace the saved profile";
    await drafts.save(previous);

    // Drain promise reactions after the real abort event, without a time-based wait.
    const nextTask = () => new Promise(resolve => {
      const channel = new MessageChannel();
      channel.port1.onmessage = () => { channel.port1.close(); channel.port2.close(); resolve(); };
      channel.port2.postMessage(null);
    });
    const abortAfterPutSuccess = async (store, operation) => {
      const originalPut = IDBObjectStore.prototype.put;
      const events = [];
      let outcome = "pending", error = "", closed = false, observedAbort;
      const aborted = new Promise(resolve => { observedAbort = resolve; });
      IDBObjectStore.prototype.put = function (...args) {
        const request = originalPut.apply(this, args);
        if (this.name === store && this.transaction.db.name === "pps-designer") {
          IDBObjectStore.prototype.put = originalPut;
          const transaction = this.transaction, database = transaction.db;
          const originalClose = database.close;
          database.close = function () { closed = true; return originalClose.call(this); };
          transaction.addEventListener("error", () => events.push("error"));
          transaction.addEventListener("complete", () => events.push("complete"));
          transaction.addEventListener("abort", () => { events.push("abort"); observedAbort(); }, { once: true });
          request.addEventListener("success", () => { events.push("put-success"); transaction.abort(); }, { once: true });
        }
        return request;
      };
      try {
        operation().then(() => { outcome = "fulfilled"; }, reason => { outcome = "rejected"; error = reason.message; });
        await aborted;
        await nextTask();
        return { outcome, error, events, closed };
      } finally { IDBObjectStore.prototype.put = originalPut; }
    };

    let savedEvents = 0;
    const saved = () => savedEvents++;
    document.addEventListener("pps-designer-saved", saved);
    const draft = await abortAfterPutSuccess("drafts", () => drafts.save(attempted));
    document.removeEventListener("pps-designer-saved", saved);
    draft.savedEvents = savedEvents;
    draft.previousRetained = JSON.stringify(await drafts.load()) === JSON.stringify(previous);
    draft.liveRetained = JSON.stringify(window.PPSDesignerApp.getState()) === JSON.stringify(originalState);
    await drafts.save(attempted);
    draft.retrySaved = (await drafts.load()).design.name === attempted.design.name;
    await drafts.save(previous);

    // Valid one-sample mono PCM WAV; overwrite the same content identity with a new source name.
    const bytes = new Uint8Array(46), view = new DataView(bytes.buffer);
    bytes.set(new TextEncoder().encode("RIFF"), 0); view.setUint32(4, 38, true);
    bytes.set(new TextEncoder().encode("WAVEfmt "), 8); view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 44100, true);
    view.setUint32(28, 88200, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    bytes.set(new TextEncoder().encode("data"), 36); view.setUint32(40, 2, true);
    const first = await drafts.storeAudio(new File([bytes], "Original.wav", { type: "audio/wav" }));
    URL.revokeObjectURL(first.url);
    const file = new File([bytes], "Replacement.wav", { type: "audio/wav" });
    const audio = await abortAfterPutSuccess("assets", () => drafts.storeAudio(file));
    audio.previousRetained = (await drafts.asset(first.id)).name === "Original.wav";
    audio.draftRetained = JSON.stringify(await drafts.load()) === JSON.stringify(previous);
    const retry = await drafts.storeAudio(file);
    URL.revokeObjectURL(retry.url);
    audio.retrySaved = (await drafts.asset(retry.id)).name === "Replacement.wav";
    return { draft, audio };
  });
  await writeFile(evidencePath, JSON.stringify(evidence, null, 2));
  for (const [kind, result] of Object.entries(evidence)) {
    assert.deepEqual(result.events, ["put-success", "abort"], `${kind}: abort is after request success, with no error event`);
    assert.equal(result.outcome, "rejected", `${kind}: transaction abort must settle the write promise`);
    assert.match(result.error, /abort/i);
    assert.equal(result.closed, true, `${kind}: failed transaction releases its connection`);
    assert.equal(result.previousRetained, true);
    assert.equal(result.retrySaved, true);
  }
  assert.equal(evidence.draft.savedEvents, 0, "an aborted draft never announces a successful save");
  assert.equal(evidence.draft.liveRetained, true);
  assert.equal(evidence.audio.draftRetained, true);
}
