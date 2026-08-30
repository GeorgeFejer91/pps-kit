import assert from "node:assert/strict";
import test from "node:test";

import { selectRunnerAdapter } from "../src/api/runner-api.js";

test("RunnerApi selects native Tauri only when the invoke bridge exists", () => {
  assert.equal(selectRunnerAdapter({}).kind, "browser-preview");
  assert.equal(selectRunnerAdapter({ __TAURI_INTERNALS__: {} }).kind, "browser-preview");
  assert.equal(selectRunnerAdapter({ __TAURI_INTERNALS__: { invoke() {} } }).kind, "tauri-native");
});

test("ordinary-browser preview supports deterministic local clicks and fails remote enable closed", async () => {
  const adapter = selectRunnerAdapter({});
  const first = await adapter.snapshot();
  const second = await adapter.snapshot();
  assert.deepEqual(first, second);

  const prepared = await adapter.dispatch("package.prepare_demo", {});
  assert.equal(prepared.status, "accepted");
  assert.equal(prepared.snapshot.package_verified, true);
  assert.equal(prepared.resulting_revision, 1);

  await assert.rejects(
    () => adapter.configureRemote({ enabled: true, allowAbort: false }),
    /disabled in ordinary-browser preview/u,
  );
  const status = await adapter.remoteStatus();
  assert.equal(status.enabled, false);
  assert.equal(status.controllerUrl, "");
});
