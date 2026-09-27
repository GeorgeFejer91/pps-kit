import assert from "node:assert/strict";
import test from "node:test";

import { selectRunnerAdapter } from "../src/api/runner-api.js";
import { createTauriRunnerAdapter } from "../src/api/tauri-runner-adapter.js";

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

  for (const operation of [
    "remoteSessionClaim",
    "remoteSessionRenew",
    "remoteSessionDispatch",
    "remoteSessionRevoke",
  ]) {
    await assert.rejects(() => adapter[operation]({}), /native remote authority is unavailable/iu);
  }
  await assert.rejects(
    () => adapter.selectPreparedSession(),
    /available only in the native Tauri runner/iu,
  );
  await assert.rejects(
    () => adapter.inspectPreparedExecution(),
    /available only in the native Tauri runner/iu,
  );
  await assert.rejects(
    () => adapter.prepareFirstAudioBlock(),
    /available only in the Tauri runner/iu,
  );
  await assert.rejects(() => adapter.recordResponse(), /only in the native Tauri runner/iu);
});

test("Tauri adapter sends exact remote-owner DTOs and keeps LAN activation explicit", async () => {
  const calls = [];
  const adapter = createTauriRunnerAdapter({
    invokeFn: async (command, args) => {
      calls.push([command, args]);
      return { command, args };
    },
  });
  const command = {
    commandId: "cmd_12345678",
    scope: "session.transport",
    action: "run.pause",
    args: {},
    expectedRevision: 7,
  };

  await adapter.configureRemote({ enabled: true, allowAbort: false, lanListener: false });
  await adapter.selectPreparedSession();
  await adapter.inspectPreparedExecution();
  await adapter.prepareFirstAudioBlock();
  await adapter.remoteSessionClaim({
    sessionId: "session_12345678",
    controllerId: "controller_12345678",
    acceptedScopes: ["session.read", "session.transport"],
    readySequence: 2,
  });
  await adapter.remoteSessionRenew({
    sessionId: "session_12345678",
    ownerToken: "owner_12345678",
    controlSequence: 3,
  });
  await adapter.remoteSessionDispatch({
    sessionId: "session_12345678",
    ownerToken: "owner_12345678",
    controlSequence: 4,
    command,
  });
  await adapter.remoteSessionRevoke({
    sessionId: "session_12345678",
    ownerToken: "owner_12345678",
  });

  assert.deepEqual(calls, [
    ["configure_remote", { enabled: true, allowAbort: false, lanListener: false }],
    ["select_prepared_session", undefined],
    ["inspect_prepared_execution", undefined],
    ["prepare_first_audio_block", undefined],
    ["remote_session_claim", { request: {
      sessionId: "session_12345678",
      controllerId: "controller_12345678",
      acceptedScopes: ["session.read", "session.transport"],
      readySequence: 2,
    } }],
    ["remote_session_renew", { request: {
      sessionId: "session_12345678",
      ownerToken: "owner_12345678",
      controlSequence: 3,
    } }],
    ["remote_session_dispatch", { request: {
      sessionId: "session_12345678",
      ownerToken: "owner_12345678",
      controlSequence: 4,
      command,
    } }],
    ["remote_session_revoke", { request: {
      sessionId: "session_12345678",
      ownerToken: "owner_12345678",
    } }],
  ]);
});

test("Tauri adapter preserves sanitized native error codes", async () => {
  const adapter = createTauriRunnerAdapter({
    invokeFn: async () => { throw { code: "stale_owner", message: "The owner expired." }; },
  });
  await assert.rejects(
    () => adapter.remoteSessionRevoke({ sessionId: "session_12345678", ownerToken: "owner_12345678" }),
    (error) => error instanceof Error && error.code === "stale_owner" && error.message === "The owner expired.",
  );
});

test("participant input sends only position and choice, never caller identity or timing", async () => {
  const calls = [];
  const adapter = createTauriRunnerAdapter({ invokeFn: async (...args) => { calls.push(args); return 7; } });
  assert.equal(await adapter.recordResponse({ choice: "", x: 0.25, y: 0.75,
    eventId: 999, monotonicNs: 123, blockNumber: 2 }), 7);
  assert.deepEqual(calls, [["runner_record_response", { request: { choice: "", x: 0.25, y: 0.75 } }]]);
});

test("native state subscriptions target the local main window and retain cleanup", async () => {
  let listener;
  let stopped = false;
  const adapter = createTauriRunnerAdapter({ listenFn: async (event, handler, options) => {
    assert.equal(event, "runner-snapshot");
    assert.deepEqual(options, { target: { kind: "WebviewWindow", label: "main" } });
    listener = handler;
    return () => { stopped = true; };
  } });
  let received;
  const stop = await adapter.subscribeSnapshots((snapshot) => { received = snapshot; });
  listener({ payload: { revision: 12 } });
  assert.deepEqual(received, { revision: 12 });
  stop();
  assert.equal(stopped, true);
});

test("local output preflight sends exact native fences and cannot set execution flags", async () => {
  const calls = [];
  const adapter = createTauriRunnerAdapter({ invokeFn: async (...args) => { calls.push(args); } });
  await adapter.nativeOutputStatus();
  await adapter.enumerateNativeOutput();
  await adapter.reserveNativeOutput({ policyGeneration: "8", serviceGeneration: "1", inventoryGeneration: "4",
    deviceOrdinal: 0, configOrdinal: 1, channels: 3, sampleRateHz: 48000,
    executable: true, qualified: true, bufferFrames: 1, warmupTimeoutMs: 0, path: "private" });
  await adapter.releaseNativeOutput({ policyGeneration: "8", serviceGeneration: "1", reservationGeneration: "5",
    executable: true, path: "private" });
  await adapter.disableNativeOutput();
  assert.deepEqual(calls, [
    ["native_output_status", undefined],
    ["native_output_enumerate", undefined],
    ["native_output_reserve_silence", { request: { policyGeneration: "8", serviceGeneration: "1", inventoryGeneration: "4",
      deviceOrdinal: 0, configOrdinal: 1, channels: 3, sampleRateHz: 48000, bufferFrames: null, warmupTimeoutMs: 3000 } }],
    ["native_output_release", { request: { policyGeneration: "8", serviceGeneration: "1", reservationGeneration: "5" } }],
    ["native_output_disable", undefined],
  ]);
});
