import assert from "node:assert/strict";
import test from "node:test";
import { createNativeSnapshotOrder } from "../src/ui/native-snapshot-order.js";

test("native snapshot order accepts random new epochs and retires old events", () => {
  const accept = createNativeSnapshotOrder();
  assert.equal(accept({ epoch: 400, revision: 1 }), true);
  assert.equal(accept({ epoch: 400, revision: 0 }), false);
  assert.equal(accept({ epoch: 12, revision: 3 }), true);
  assert.equal(accept({ epoch: 400, revision: 2 }), false);
  assert.equal(accept({ epoch: 12, revision: 4 }), true);
  assert.equal(accept({ epoch: 12, revision: 3 }), false);
  assert.equal(accept({ epoch: 9, revision: 1 }), true);
  assert.equal(accept({ epoch: 12, revision: 5 }), false);
});
