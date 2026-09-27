import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { ALL_ACTIONS, PROTOCOL, PROTOCOL_VERSION, requiredScope, isRemoteAction } from "../src/domain/runner-contract.js";

test("browser action permissions match the shared native protocol fixture", async () => {
  const fixture = JSON.parse(await readFile(new URL("../../../../packages/pps-contracts/fixtures/remote-actions.v1.json", import.meta.url), "utf8"));
  assert.equal(PROTOCOL, fixture.protocol);
  assert.equal(PROTOCOL_VERSION, fixture.version);
  assert.deepEqual([...ALL_ACTIONS].sort(), Object.keys(fixture.actions).sort());
  for (const [action, scope] of Object.entries(fixture.actions)) {
    assert.equal(requiredScope(action), scope);
    assert.equal(isRemoteAction(action), scope !== null);
  }
});
