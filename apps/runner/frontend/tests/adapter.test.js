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
