import assert from "node:assert/strict";
import test from "node:test";
import { createNativeDesigner } from "../native_designer.js";

globalThis.document = new EventTarget();
test("native failures stay native and a rejected capability does not prevent a later save", async () => {
  const calls = [];
  const adapter = createNativeDesigner(async (command, args) => {
    calls.push({ command, args });
    if (command === "designer_snapshot") return { revision: 4, snapshot: null };
    if (command === "designer_generate") throw new Error("explicit_source_algorithm_required");
    if (command === "designer_save") { assert.equal(args.expectedRevision, 4); return 5; }
    throw new Error(`Unexpected command ${command}`);
  }, true);
  await adapter.load();
  await assert.rejects(adapter.generate({ design: {} }, {}, { accept_non_legacy_source_algorithm: false }), /explicit_source_algorithm_required/);
  await adapter.save({ design: { name: "Retryable draft" } });
  assert.deepEqual(calls.map(call => call.command), ["designer_snapshot", "designer_generate", "designer_save"]);
  assert.equal(calls[1].args.optIn.accept_non_legacy_source_algorithm, false);
});

test("native publication cannot replace a draft changed while generation was pending", async () => {
  const calls = [];
  let started;
  const ready = new Promise(resolve => { started = resolve; });
  const adapter = createNativeDesigner(async (command, args) => {
    calls.push(command);
    if (command === "designer_snapshot") return { revision: 3, snapshot: { design: { name: "Old generated state" } } };
    if (command === "designer_generate") { started(); return { job_id: "1" }; }
    if (command === "designer_invalidate") { assert.equal(args.expectedRevision, 3); return 4; }
    if (command === "designer_job") return { status: "succeeded", result: {} };
    throw new Error(command);
  }, true);
  await adapter.load();
  const pending = adapter.generate({ design: {} }, {}, {});
  await ready;
  adapter.invalidate();
  await assert.rejects(pending, /draft changed/);
  assert.ok(calls.includes("designer_invalidate"));
});

test("native cancellation sends only the bounded cancellation command", async () => {
  let started;
  const ready = new Promise(resolve => { started = resolve; });
  const calls = [];
  const adapter = createNativeDesigner(async command => {
    calls.push(command);
    if (command === "designer_generate") { started(); return { job_id: "2" }; }
    if (command === "designer_cancel") return;
    if (command === "designer_job") return { status: "cancelled", message: "Cancelled" };
    throw new Error(command);
  }, true);
  const pending = adapter.generate({ design: {} }, {}, {});
  await ready;
  await new Promise(resolve => setTimeout(resolve, 0));
  await adapter.cancel();
  await assert.rejects(pending, /Cancelled/);
  assert.deepEqual(calls, ["designer_generate", "designer_cancel", "designer_job"]);
});

test("cancellation requested while a native start is pending reaches the newly allocated job", async () => {
  let completeStart, started;
  const ready = new Promise(resolve => { started = resolve; });
  const calls=[];
  const adapter=createNativeDesigner(async command=>{
    calls.push(command);
    if(command === "designer_review") { started(); return new Promise(resolve=>{completeStart=resolve;}); }
    if(command === "designer_cancel") return;
    if(command === "designer_job") return {status:"cancelled",message:"Cancelled before publication"};
    throw new Error(command);
  },true);
  const running=adapter.review({design:{}},[]);
  await ready;
  const cancellation=adapter.cancel();
  completeStart({job_id:"pending-start"});
  await cancellation;
  await assert.rejects(running,/Cancelled before publication/);
  assert.deepEqual(calls,["designer_review","designer_cancel","designer_job"]);
});


test("native assembly bounds come from the current host snapshot", async () => {
  let capabilities = { assembly: { max_rows: 10000, max_blocks: 128 } };
  const adapter = createNativeDesigner(async () => ({ revision: 1, capabilities }), true);
  assert.equal(adapter.capabilities, null);
  await adapter.load();
  assert.deepEqual(adapter.capabilities, capabilities);
  capabilities = undefined;
  await adapter.load();
  assert.equal(adapter.capabilities, null, "missing capabilities cannot reuse stale authority");
});
