import assert from "node:assert/strict";
import test from "node:test";
import { bindParticipantSetupDraft } from "../src/ui/participant-setup-draft.js";

function setup() {
  const elements = Object.fromEntries(["participant-code", "participant-name", "participant-age",
    "participant-handedness", "participant-gender", "name-sharing"].map(id => [id, Object.assign(new EventTarget(), { value: "", checked: false })]));
  const draft = bindParticipantSetupDraft(elements);
  const snapshot = { target_id: "runner", epoch: 1, setup: { participant_code: "", age: null,
    handedness: "unspecified", gender: "unspecified", name_sharing_opt_in: false } };
  draft.refresh(snapshot);
  const edit = (id, value) => {
    elements[id][id === "name-sharing" ? "checked" : "value"] = value;
    elements[id].dispatchEvent(new Event("input"));
  };
  return { elements, draft, snapshot, edit };
}

test("polls preserve all edited participant fields after focus moves", () => {
  const { draft, snapshot, edit } = setup();
  edit("participant-code", "LOCAL-002");
  edit("participant-age", "38");
  edit("participant-handedness", "left");
  edit("participant-gender", "prefer_not_to_say");
  edit("participant-name", "Private local name");
  edit("name-sharing", true);
  for (let i = 0; i < 4; i++) draft.refresh(snapshot);
  assert.deepEqual(draft.capture().values, { participant_code: "LOCAL-002", participant_name: "Private local name",
    age: "38", handedness: "left", gender: "prefer_not_to_say", name_sharing_opt_in: true });
});

test("only acknowledged, unchanged fields return to native ownership", () => {
  const { draft, snapshot, elements, edit } = setup();
  edit("participant-code", " A ");
  edit("participant-age", "38");
  const submission = draft.capture();
  draft.refresh(snapshot);
  assert.equal(elements["participant-code"].value, " A ", "unacknowledged or rejected submit preserves the draft");
  edit("participant-age", "39");
  snapshot.setup = { ...snapshot.setup, participant_code: "A", age: 38, gender: "female" };
  draft.acknowledge(submission);
  draft.refresh(snapshot);
  assert.equal(elements["participant-code"].value, "A");
  assert.equal(elements["participant-age"].value, "39", "new edits survive a delayed success");
  assert.equal(elements["participant-gender"].value, "female", "unedited fields follow native changes");
});

test("a new native epoch resets drafts and rejects old submit acknowledgements", () => {
  const { draft, snapshot, elements, edit } = setup();
  edit("participant-name", "Private local name");
  edit("name-sharing", true);
  const old = draft.capture();
  draft.refresh({ ...snapshot, epoch: 2 });
  assert.equal(elements["participant-name"].value, "");
  assert.equal(elements["name-sharing"].checked, false);
  edit("participant-code", "NEXT");
  draft.acknowledge(old);
  draft.refresh({ ...snapshot, epoch: 2 });
  assert.equal(elements["participant-code"].value, "NEXT");
});
