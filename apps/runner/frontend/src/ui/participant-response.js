// Input only: the native authority supplies identity, timestamps and scoring.
export function bindParticipantResponse({ target, api, onError, liveState, choiceControls = null, choiceButtons = {}, help = null }) {
  let snapshot = null;
  let responseMode = "go";
  let available = false;
  const active = phase => ["running", "paused"].includes(phase);
  const clickGate = () => snapshot?.run?.phase === "instruction_gate"
    && snapshot?.instruction_gate?.waiting === true
    && snapshot?.instruction_gate?.next_action === "continue-click";
  const refresh = (next = snapshot) => {
    if (snapshot && (next?.identity?.session_id !== snapshot.identity?.session_id
      || (active(snapshot.run?.phase) && !active(next?.run?.phase)))) responseMode = "go";
    snapshot = next;
    available = api.kind === "tauri-native" && liveState() && document.visibilityState === "visible"
      && (clickGate() || (snapshot?.run?.phase === "running" && snapshot?.run?.participant_capture_ready === true));
    const choiceMode = !clickGate() && responseMode === "left_right";
    const unsupported = !clickGate() && responseMode === "unsupported";
    target.hidden = choiceMode;
    target.disabled = !available || choiceMode || unsupported;
    target.textContent = clickGate() ? "Continue instruction" : unsupported ? "Response mode unavailable" : "Respond";
    if (choiceControls) choiceControls.hidden = !choiceMode;
    for (const button of Object.values(choiceButtons)) button.disabled = !available || !choiceMode;
    if (help) help.textContent = clickGate() ? "Activate Continue instruction to proceed."
      : unsupported ? "This prepared block requires response controls that this preview does not support."
      : choiceMode ? "Choose Left or Right. With either response button focused, use Arrow Left or Arrow Right; Space or Enter activates the focused choice."
      : "Click or tap Respond. Space or Enter records a response without a position. Responses are enabled during native playback or an instruction click gate.";
  };
  const submit = (request) => {
    refresh();
    if (!available || (!clickGate() && (responseMode === "unsupported"
      || (responseMode === "left_right" && !["left", "right"].includes(request.choice))))) return;
    // A rejected or unanswered input is never replayed as a later response.
    void api.recordResponse(clickGate() ? { choice: "", x: 0.5, y: 0.5 } : request).catch(onError);
  };
  target.addEventListener("pointerdown", (event) => {
    if (target.hidden) return;
    if (!event.isPrimary || event.button !== 0) return;
    const box = target.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width;
    const y = (event.clientY - box.top) / box.height;
    if (![x, y].every((value) => Number.isFinite(value) && value >= 0 && value <= 1)) return;
    submit({ choice: "", x, y });
  });
  target.addEventListener("click", (event) => {
    // Semantic button activation covers keyboard and assistive technology;
    // pointer responses were already captured at pointerdown.
    if (!target.hidden && event.detail === 0 && !event.pointerType) submit({ choice: "", x: null, y: null });
  });
  target.addEventListener("keydown", (event) => {
    if (event.repeat && ["Enter", " "].includes(event.key)) event.preventDefault();
  });
  for (const [choice, button] of Object.entries(choiceButtons)) {
    button.addEventListener("pointerdown", event => {
      if (responseMode === "left_right" && !clickGate() && event.isPrimary && event.button === 0) submit({ choice, x: null, y: null });
    });
    button.addEventListener("click", event => {
      if (responseMode === "left_right" && !clickGate() && event.detail === 0 && !event.pointerType) submit({ choice, x: null, y: null });
    });
    button.addEventListener("keydown", event => {
      const arrowChoice = { ArrowLeft: "left", ArrowRight: "right" }[event.key];
      if (arrowChoice && responseMode === "left_right" && !clickGate()) {
        event.preventDefault();
        if (!event.repeat) submit({ choice: arrowChoice, x: null, y: null });
      } else if (event.repeat && ["Enter", " "].includes(event.key)) event.preventDefault();
    });
  }
  const setPreparedMedia = media => {
    if (media) {
      const mode = media.responseMode ?? media.response_mode ?? "go";
      const choices = media.responseChoices ?? media.response_choices ?? [];
      responseMode = mode === "go" ? "go"
        : mode === "left_right" && Array.isArray(choices) && choices.length === 2
          && choices.includes("left") && choices.includes("right") ? "left_right" : "unsupported";
    } else if (!active(snapshot?.run?.phase)) responseMode = "go";
    refresh();
  };
  document.addEventListener("visibilitychange", () => refresh());
  refresh();
  return { refresh, setPreparedMedia };
}
