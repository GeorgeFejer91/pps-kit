const QUIESCENT_PHASES = new Set(["idle", "prepared", "completed", "interrupted", "error"]);
const PHASES = new Set(["idle", "enumerating", "enumerated", "reserving-silence", "reserved-silence",
  "reserved-media", "cleanup-pending", "disabled", "faulted", "quarantined"]);
const generation = (value) => typeof value === "string" && /^(0|[1-9]\d{0,19})$/u.test(value)
  && BigInt(value) <= 18446744073709551615n;

// One local view of the existing native preflight owner. It never enables playback.
export function bindNativeOutputSetup({ elements, api, onError, onRetireMedia }) {
  const list = elements["native-output-list"];
  const route = elements["native-output-route"];
  const prepare = elements["native-output-prepare"];
  const release = elements["native-output-release"];
  const disable = elements["native-output-disable"];
  const detail = elements["native-output-detail"];
  const selection = elements["native-output-selection"];
  let snapshot = null, media = null, status = null, inventory = null, choices = [];
  let context = 0, busy = false, suspended = false, refreshing = null;
  const native = api.kind === "tauri-native";
  const quiescent = () => snapshot?.safety?.local_armed === false
    && QUIESCENT_PHASES.has(snapshot?.run?.phase);
  const currentInventory = () => inventory && status
    && inventory.policyGeneration === status.policyGeneration
    && inventory.serviceGeneration === status.serviceGeneration
    && inventory.inventoryGeneration === status.inventoryGeneration;

  function render() {
    const reserved = Boolean(status?.reservationGeneration);
    const available = native && !suspended && quiescent() && media && !busy
      && status && !status.inFlight && !status.cleanupPending
      && status.phase !== "quarantined" && !reserved;
    list.disabled = !available;
    route.disabled = !available || !currentInventory();
    prepare.disabled = route.disabled || !choices[Number(route.value)] || route.value === "";
    release.disabled = !native || !reserved;
    disable.disabled = !native;
    selection.textContent = choices[Number(route.value)] && route.value !== ""
      ? choices[Number(route.value)].label : "Choose a device configuration matching the prepared block.";
    detail.textContent = !native ? "Output preparation is available in the native Runner."
      : busy ? "Preparing native output. No experiment playback is enabled."
      : !status ? "Native output status is unavailable."
      : status.phase === "reserved-media" ? "Prepared and silent. Experiment activation is still unavailable; this device route is unqualified."
      : status.phase === "reserved-silence" ? "Silent device reserved without media. Release it before preparing the current block."
      : status.phase === "cleanup-pending" ? "Releasing native output. Wait for cleanup before preparing another device."
      : ["faulted", "quarantined"].includes(status.phase) ? "Native output failed. Disable output and inspect the device before preparing again."
      : !quiescent() ? "Disarm and stop the run before changing the output device."
      : !media ? "Prepare the first audio block before listing compatible output devices."
      : currentInventory() && !choices.length ? "No listed configuration matches this block's channels and sample rate. Check the device, then list again."
      : "List devices, choose a matching configuration, then prepare silent output. Playback and route qualification remain separate.";
  }

  function clearInventory() {
    inventory = null;
    choices = [];
    route.replaceChildren(new Option("Choose output device…", ""));
  }

  function acceptStatus(candidate) {
    if (candidate?.schema !== "pps-runner-native-output-preflight.v1"
      || !PHASES.has(candidate.phase)
      || ![candidate.policyGeneration, candidate.serviceGeneration, candidate.operationGeneration].every(generation)
      || ![candidate.inventoryGeneration, candidate.reservationGeneration].every(value => value === null || generation(value))
      || typeof candidate.inFlight !== "boolean" || typeof candidate.cleanupPending !== "boolean"
      || candidate.silenceOnly !== true || candidate.executable !== false
      || candidate.armed !== false || candidate.qualified !== false) {
      throw new Error("The native Runner returned an invalid output-preparation status.");
    }
    status = candidate;
    if (inventory && !currentInventory()) clearInventory();
    render();
  }

  async function refresh() {
    if (!native || busy || suspended) return;
    if (refreshing) return refreshing;
    const token = context;
    refreshing = (async () => {
      try {
        const candidate = await api.nativeOutputStatus();
        if (token === context) acceptStatus(candidate);
      } catch (error) {
        if (token === context) { status = null; clearInventory(); render(); }
        throw error;
      } finally { refreshing = null; }
    })();
    return refreshing;
  }

  async function operate(operation, apply = () => {}) {
    if (busy) return;
    const token = ++context;
    busy = true;
    render();
    try {
      const result = await operation();
      if (token === context) apply(result);
    } catch (error) {
      if (token === context) { clearInventory(); onError(error); }
    } finally {
      if (token === context) busy = false;
      if (refreshing) await refreshing.catch(() => {});
      await refresh().catch(() => {});
      render();
    }
  }

  list.addEventListener("click", () => {
    if (list.disabled) return;
    void operate(() => api.enumerateNativeOutput(), candidate => {
      if (candidate?.schema !== "pps-runner-native-output-inventory.v1" || !Array.isArray(candidate.devices)
        || ![candidate.policyGeneration, candidate.serviceGeneration, candidate.inventoryGeneration].every(generation)
        || candidate.executable !== false || candidate.qualified !== false || candidate.armed !== false) {
        throw new Error("The native Runner returned an invalid output-device inventory.");
      }
      clearInventory();
      inventory = candidate;
      const sampleRate = media.sampleRateHz ?? media.sample_rate_hz;
      const channels = media.sourceChannels ?? media.source_channels;
      for (const device of candidate.devices) for (const config of device.f32Configs ?? []) {
        if (config.sampleFormat !== "f32" || config.channels !== channels
          || sampleRate < config.minimumSampleRateHz || sampleRate > config.maximumSampleRateHz) continue;
        const label = `${device.displayName} · ${channels} channels · ${sampleRate.toLocaleString()} Hz`;
        choices.push({ label, deviceOrdinal: device.deviceOrdinal, configOrdinal: config.configOrdinal,
          channels, sampleRateHz: sampleRate });
        route.add(new Option(label, String(choices.length - 1)));
      }
    });
  });
  route.addEventListener("change", render);
  prepare.addEventListener("click", () => {
    if (prepare.disabled || !currentInventory()) return;
    const choice = choices[Number(route.value)];
    void operate(() => api.reserveNativeOutput({ ...choice,
      policyGeneration: inventory.policyGeneration, serviceGeneration: inventory.serviceGeneration,
      inventoryGeneration: inventory.inventoryGeneration }));
  });
  release.addEventListener("click", () => {
    if (release.disabled) return;
    const request = { ...status };
    context++;
    busy = false;
    clearInventory();
    onRetireMedia();
    void operate(() => api.releaseNativeOutput(request));
  });
  disable.addEventListener("click", async () => {
    if (disable.disabled) return;
    context++;
    busy = false;
    status = null;
    clearInventory();
    onRetireMedia();
    const token = ++context;
    render();
    try {
      const result = await api.disableNativeOutput();
      if (token === context) acceptStatus(result);
    }
    catch (error) { onError(error); }
    if (refreshing) await refreshing.catch(() => {});
    await refresh().catch(() => {});
  });

  clearInventory();
  render();
  return { refresh, suspend() {
    suspended = true;
    context++;
    busy = false;
    status = null;
    clearInventory();
    render();
  }, async resume() {
    suspended = false;
    if (refreshing) await refreshing.catch(() => {});
    await refresh();
  }, update(nextSnapshot, nextMedia) {
    if (nextMedia !== media || snapshot?.epoch !== nextSnapshot?.epoch
      || snapshot?.identity?.session_id !== nextSnapshot?.identity?.session_id) {
      context++;
      busy = false;
      clearInventory();
    }
    snapshot = nextSnapshot;
    media = nextMedia;
    render();
  } };
}
