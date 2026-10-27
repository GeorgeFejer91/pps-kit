const FIELD_IDS = {
  participant_code: "participant-code",
  participant_name: "participant-name",
  age: "participant-age",
  handedness: "participant-handedness",
  gender: "participant-gender",
  name_sharing_opt_in: "name-sharing",
};

export function bindParticipantSetupDraft(elements) {
  const dirty = new Set();
  let context = null;
  const read = (key) => key === "name_sharing_opt_in"
    ? elements[FIELD_IDS[key]].checked : elements[FIELD_IDS[key]].value;
  for (const [key, id] of Object.entries(FIELD_IDS)) {
    for (const event of ["input", "change"]) elements[id].addEventListener(event, () => dirty.add(key));
  }

  return {
    refresh(snapshot) {
      const nextContext = JSON.stringify([snapshot.target_id, snapshot.epoch]);
      if (context !== null && nextContext !== context) {
        dirty.clear();
        elements[FIELD_IDS.participant_name].value = "";
      }
      context = nextContext;
      for (const [key, id] of Object.entries(FIELD_IDS)) {
        if (dirty.has(key) || key === "participant_name") continue;
        const value = snapshot.setup?.[key];
        if (key === "name_sharing_opt_in") elements[id].checked = Boolean(value);
        else elements[id].value = value == null || (["handedness", "gender"].includes(key) && value === "unspecified") ? "" : String(value);
      }
    },
    capture() {
      return { context, values: Object.fromEntries(Object.keys(FIELD_IDS).map(key => [key, read(key)])) };
    },
    acknowledge(submission) {
      if (submission.context !== context) return;
      for (const [key, value] of Object.entries(submission.values)) {
        if (read(key) === value) dirty.delete(key);
      }
    },
  };
}
