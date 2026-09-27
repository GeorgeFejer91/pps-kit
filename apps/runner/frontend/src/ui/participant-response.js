// Input only: the native authority supplies identity, timestamps and scoring.
export function bindParticipantResponse({ target, api, onError, liveState }) {
  let snapshot = null;
  const refresh = (next = snapshot) => {
    snapshot = next;
    target.disabled = api.kind !== "tauri-native"
      || !liveState()
      || snapshot?.run?.phase !== "running"
      || snapshot?.run?.participant_capture_ready !== true
      || document.visibilityState !== "visible";
  };
  const submit = (request) => {
    refresh();
    if (target.disabled) return;
    // A rejected or unanswered input is never replayed as a later response.
    void api.recordResponse(request).catch(onError);
  };
  target.addEventListener("pointerdown", (event) => {
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
    if (event.detail === 0 && !event.pointerType) submit({ choice: "", x: null, y: null });
  });
  target.addEventListener("keydown", (event) => {
    if (event.repeat && ["Enter", " "].includes(event.key)) event.preventDefault();
  });
  document.addEventListener("visibilitychange", () => refresh());
  refresh();
  return { refresh };
}
