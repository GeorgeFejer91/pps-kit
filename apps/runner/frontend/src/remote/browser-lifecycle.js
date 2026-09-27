/** Pair suspension with recovery; neither callback should replay experiment actions. */
export function installBrowserLifecycle({
  suspend,
  resume,
  windowObject = window,
  documentObject = document,
  navigatorObject = navigator,
}) {
  let suspended = false;
  const pause = () => {
    if (suspended) return;
    suspended = true;
    suspend();
  };
  const recover = () => {
    if (!suspended || documentObject.visibilityState !== "visible"
      || navigatorObject.onLine === false) return;
    suspended = false;
    resume();
  };
  documentObject.addEventListener("visibilitychange", () => {
    if (documentObject.visibilityState === "visible") recover();
    else pause();
  });
  documentObject.addEventListener("freeze", pause);
  documentObject.addEventListener("resume", recover);
  windowObject.addEventListener("pagehide", pause);
  windowObject.addEventListener("pageshow", recover);
  windowObject.addEventListener("offline", pause);
  windowObject.addEventListener("online", recover);
  if (documentObject.visibilityState !== "visible" || navigatorObject.onLine === false) pause();
}
