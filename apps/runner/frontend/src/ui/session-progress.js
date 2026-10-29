const count = value => Number.isSafeInteger(value) && value >= 0;
const PAGE_SIZE = 8;

export function validGroupStatus(value) {
  return value && count(value.revision) && count(value.partCount) && value.partCount <= 2
    && count(value.currentPart) && value.currentPart <= value.partCount
    && count(value.completedParts) && value.completedParts <= value.partCount
    && typeof value.experimentComplete === "boolean"
    && (value.publicationStatus === undefined || ["not_started", "publishing", "complete", "failed"].includes(value.publicationStatus))
    && (value.partCount === 0 ? value.currentPart === 0 && value.completedParts === 0 && !value.experimentComplete
      : value.currentPart > 0 && (!value.experimentComplete || value.completedParts === value.partCount));
}

export function validResultsAssessment(value) {
  return value?.schema === "pps.native-result-assessment.v1"
    && value.inspectionScope === "read-only-file-prefix" && value.timingQualification === "unqualified"
    && typeof value.completeScan === "boolean" && typeof value.reason === "string"
    && Array.isArray(value.attempts) && value.attempts.length <= 256
    && value.attempts.every(attempt => /^[A-Za-z0-9_-]{32}$/u.test(attempt.attemptId)
      && ["complete", "interrupted", "orphaned", "invalid"].includes(attempt.status)
      && typeof attempt.reason === "string" && count(attempt.commonEventRecords) && count(attempt.commonDatasetRows)
      && (attempt.commonEventSequence === null || count(attempt.commonEventSequence)));
}

export function validGroupResultsAssessment(value) {
  return value?.schema === "pps.native-group-result-assessment.v1" && value.timingQualification === "unqualified"
    && typeof value.completeScan === "boolean" && typeof value.reason === "string"
    && Array.isArray(value.parts) && value.parts.length <= 2
    && new Set(value.parts.map(part => part.partNumber)).size === value.parts.length
    && value.parts.every(part => [1, 2].includes(part.partNumber) && validResultsAssessment(part.assessment))
    && Array.isArray(value.groups) && value.groups.length <= 256
    && value.groups.every(group => /^[A-Za-z0-9_-]{1,128}$/u.test(group.groupAttemptId)
      && ["complete", "invalid", "interrupted", "not_assessed"].includes(group.status) && typeof group.reason === "string"
      && [group.partCount, group.scoredTrialCount, group.datasetRowCount].every(value => value === null || count(value)));
}

// The native owner chooses parts and authorizes advancement. This module displays
// its bounded status and selection-time file assessment without reconstructing either.
export function bindSessionProgress({ elements, api, onAdvance, onError }) {
  let snapshot = null, status = null, pending = null, busy = false, selecting = false, context = 0;
  let assessment = null, groupAssessment = null, page = 0, groupPage = 0, requestedKey = "";
  const native = api.kind === "tauri-native";
  const next = elements["advance-session-part"];
  const summary = elements["session-group-status"];
  const current = () => status && status.revision === snapshot?.revision;

  function renderGroup() {
    next.hidden = !status?.partCount;
    next.disabled = !native || busy || selecting || !current() || snapshot?.run?.phase !== "completed"
      || status.experimentComplete || status.completedParts >= status.partCount || status.completedParts !== status.currentPart;
    next.textContent = status?.currentPart && status.currentPart < status.partCount ? `Load part ${status.currentPart + 1}` : "Load next part";
    summary.textContent = !native ? "Session groups are available in the native Runner."
      : !status ? "Native session-group status unavailable."
      : !status.partCount ? "Single prepared session."
      : status.experimentComplete ? `Experiment complete · ${status.partCount} of ${status.partCount} parts recorded.`
      : status.publicationStatus === "failed" ? "All parts recorded, but the native group completion receipt failed. Keep the existing result files for inspection; whole-experiment completion is unconfirmed."
      : status.completedParts === status.partCount ? `All ${status.partCount} parts recorded · waiting for the native group completion receipt.`
      : `Part ${status.currentPart} of ${status.partCount} · ${status.completedParts} complete. ${status.completedParts === status.currentPart ? "Load the next part to continue." : "Follow the native instruction and block sequence."}`;
  }

  function renderAssessment() {
    const panel = elements["native-results-assessment"];
    panel.hidden = !assessment && !groupAssessment;
    elements["native-results-summary"].textContent = assessment
      ? `${assessment.attempts.length} existing attempt${assessment.attempts.length === 1 ? "" : "s"} · ${assessment.completeScan ? "scan complete" : "partial scan"} (${assessment.reason.replaceAll("_", " ")}). File contents only; timing remains unqualified. Selection starts a new attempt; these files are not resumed.` : "";
    const attempts = assessment?.attempts ?? [];
    elements["native-results-list"].replaceChildren(...attempts.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(attempt => {
      const item = document.createElement("li");
      item.textContent = `${attempt.attemptId}: ${attempt.status} · ${attempt.commonEventRecords} common event records, ${attempt.commonDatasetRows} common dataset rows · ${attempt.reason.replaceAll("_", " ")}`;
      return item;
    }));
    elements["native-results-page"].textContent = attempts.length ? `Page ${page + 1} of ${Math.ceil(attempts.length / PAGE_SIZE)}` : "No existing result attempts found.";
    elements["native-results-previous"].disabled = page === 0;
    elements["native-results-next"].disabled = (page + 1) * PAGE_SIZE >= attempts.length;
    elements["native-group-results"].hidden = !groupAssessment;
    elements["native-results-part-label"].hidden = !groupAssessment?.parts.length;
    const groups = groupAssessment?.groups ?? [];
    elements["native-group-results-summary"].textContent = groupAssessment
      ? `${groups.length} prior group receipt${groups.length === 1 ? "" : "s"} · ${groupAssessment.completeScan ? "scan complete" : "partial scan"} (${groupAssessment.reason.replaceAll("_", " ")}). These records describe earlier attempts, not the current run. Timing remains unqualified.` : "";
    elements["native-group-results-list"].replaceChildren(...groups.slice(groupPage * PAGE_SIZE, (groupPage + 1) * PAGE_SIZE).map(group => {
      const item = document.createElement("li");
      item.textContent = `${group.groupAttemptId}: ${group.status.replaceAll("_", " ")} · ${group.partCount ?? "unknown"} parts, ${group.scoredTrialCount ?? "unknown"} scored trials, ${group.datasetRowCount ?? "unknown"} dataset rows · ${group.reason.replaceAll("_", " ")}`;
      return item;
    }));
    elements["native-group-results-page"].textContent = groups.length ? `Page ${groupPage + 1} of ${Math.ceil(groups.length / PAGE_SIZE)}` : "No prior group receipts found.";
    elements["native-group-results-previous"].disabled = groupPage === 0;
    elements["native-group-results-next"].disabled = (groupPage + 1) * PAGE_SIZE >= groups.length;
  }

  async function refresh() {
    if (!native || !snapshot || pending) return;
    const key = `${snapshot.epoch}:${snapshot.revision}:${snapshot.identity?.session_id}`;
    if (key === requestedKey) return;
    requestedKey = key;
    const token = context;
    pending = api.nativeGroupStatus();
    try {
      const candidate = await pending;
      if (!validGroupStatus(candidate)) throw new Error("The native Runner returned an invalid session-group status.");
      if (token === context && candidate.revision === snapshot.revision) status = candidate;
    } catch (error) {
      if (token === context) { status = null; requestedKey = ""; onError(error); }
    } finally {
      pending = null;
      renderGroup();
      // A newer snapshot may have arrived while this read was in flight.
      if (token !== context || key !== `${snapshot?.epoch}:${snapshot?.revision}:${snapshot?.identity?.session_id}`) void refresh();
    }
  }

  next.addEventListener("click", async () => {
    if (next.disabled) return;
    busy = true;
    const token = context;
    const expectedRevision = status.revision;
    renderGroup();
    try {
      const advanced = await api.advancePreparedGroupPart({ expectedRevision });
      if (token !== context) return;
      status = null;
      setAssessment(null);
      onAdvance(advanced);
    } catch (error) { onError(error); }
    finally { busy = false; requestedKey = ""; renderGroup(); void refresh(); }
  });
  for (const [id, delta] of [["native-results-previous", -1], ["native-results-next", 1]]) {
    elements[id].addEventListener("click", () => { if (!elements[id].disabled) { page += delta; renderAssessment(); } });
  }
  for (const [id, delta] of [["native-group-results-previous", -1], ["native-group-results-next", 1]]) {
    elements[id].addEventListener("click", () => { if (!elements[id].disabled) { groupPage += delta; renderAssessment(); } });
  }
  elements["native-results-part"].addEventListener("change", () => {
    assessment = groupAssessment?.parts.find(part => String(part.partNumber) === elements["native-results-part"].value)?.assessment ?? null;
    page = 0;
    renderAssessment();
  });
  function setAssessment(value, groupValue = null) {
    if (value && !validResultsAssessment(value)) throw new Error("The native Runner returned an invalid result-file assessment.");
    if (groupValue && !validGroupResultsAssessment(groupValue)) throw new Error("The native Runner returned an invalid group-result assessment.");
    groupAssessment = groupValue;
    assessment = groupValue?.parts[0]?.assessment ?? value;
    page = 0;
    groupPage = 0;
    elements["native-results-part"].replaceChildren(...(groupValue?.parts ?? []).map(part => {
      const option = document.createElement("option");
      option.value = String(part.partNumber);
      option.textContent = `Part ${part.partNumber}`;
      return option;
    }));
    elements["native-results-assessment"].open = Boolean(assessment?.attempts.length || groupValue?.groups.length);
    renderAssessment();
  }
  renderGroup();
  renderAssessment();
  return { setAssessment, isBusy: () => busy, setSelecting(value) { selecting = value; renderGroup(); }, update(nextSnapshot) {
    if (snapshot?.epoch !== nextSnapshot?.epoch || snapshot?.identity?.session_id !== nextSnapshot?.identity?.session_id) {
      context++; status = null; requestedKey = ""; setAssessment(null);
    }
    snapshot = nextSnapshot;
    renderGroup();
    void refresh();
  } };
}
