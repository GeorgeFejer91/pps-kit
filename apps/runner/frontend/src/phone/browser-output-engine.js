import { RESPONSE_SETTLE_MS } from "./tap-response.js";

export const DEMO_AUDIO_MS = 3_000;
export const DEMO_TACTILE_MS = 2_300;
export const DEMO_DURATION_MS = DEMO_TACTILE_MS + RESPONSE_SETTLE_MS;

function audioContextConstructor() {
  return globalThis.AudioContext || globalThis.webkitAudioContext;
}

export function audioOutputTime(context, audioTime, now = performance.now()) {
  const timestamp = context.getOutputTimestamp?.();
  if (Number.isFinite(timestamp?.contextTime) && Number.isFinite(timestamp.performanceTime) &&
      timestamp.performanceTime > 0) {
    return timestamp.performanceTime + (audioTime - timestamp.contextTime) * 1000;
  }
  return now + (audioTime - context.currentTime + (context.baseLatency ?? 0) +
    (context.outputLatency ?? 0)) * 1000;
}

export class BrowserOutputEngine extends EventTarget {
  constructor({ navigatorObject = globalThis.navigator } = {}) {
    super();
    this.navigatorObject = navigatorObject;
    this.context = null;
    this.master = null;
    this.oscillator = null;
    this.timeout = null;
    this.armed = false;
    this.armGeneration = 0;
    this.audioEnabled = true;
    this.vibrationEnabled = true;
  }

  capabilities() {
    return {
      audio: Boolean(audioContextConstructor()),
      vibration: typeof this.navigatorObject?.vibrate === "function",
    };
  }

  async arm({ audioEnabled, vibrationEnabled }) {
    this.disarm();
    const generation = this.armGeneration;
    this.audioEnabled = Boolean(audioEnabled);
    this.vibrationEnabled = Boolean(vibrationEnabled);
    if (!this.audioEnabled && !this.vibrationEnabled) throw new Error("Enable audio or vibration first.");
    if (this.vibrationEnabled) this.requestVibration(100);
    if (this.audioEnabled) {
      const Constructor = audioContextConstructor();
      if (!Constructor) throw new Error("Web Audio is unavailable on this browser.");
      this.context ??= new Constructor({ latencyHint: "interactive" });
      if (this.context.state !== "running") await this.context.resume();
      if (generation !== this.armGeneration) throw new Error("Output arming was interrupted.");
      if (this.context.state !== "running") throw new Error("Phone audio could not be started.");
      if (!this.master) {
        this.master = this.context.createGain();
        this.master.gain.value = 0.7;
        this.master.connect(this.context.destination);
      }
    }
    this.armed = true;
  }

  requestVibration(pattern) {
    const atMs = performance.now();
    if (!this.navigatorObject?.vibrate?.(pattern)) {
      throw new Error("The browser refused a vibration request. Use Android Chrome in the foreground and check vibration settings.");
    }
    return atMs;
  }

  startDemo() {
    if (!this.armed) throw new Error("Arm phone outputs locally before starting the demo.");
    this.stopDemo();
    let startAt = performance.now();
    if (this.audioEnabled && this.context && this.master) {
      if (this.context.state !== "running") throw new Error("Phone audio is suspended. Arm outputs again.");
      const now = this.context.currentTime + 0.05;
      startAt = audioOutputTime(this.context, now);
      const oscillator = this.context.createOscillator();
      const gain = this.context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(220, now);
      oscillator.frequency.exponentialRampToValueAtTime(660, now + DEMO_AUDIO_MS / 1_000);
      gain.gain.setValueAtTime(0.003, now);
      gain.gain.exponentialRampToValueAtTime(0.42, now + DEMO_AUDIO_MS / 1_000);
      oscillator.connect(gain);
      gain.connect(this.master);
      oscillator.start(now);
      oscillator.stop(now + DEMO_AUDIO_MS / 1_000);
      this.oscillator = oscillator;
    }
    const useTactile = this.vibrationEnabled && this.capabilities().vibration;
    const timers = { tactile: null, completed: null };
    this.timeout = timers;
    const finish = (atMs) => {
      timers.completed = setTimeout(() => {
        this.timeout = null;
        const event = new Event("complete");
        Object.defineProperty(event, "detail", { value: { startAt, endedAt: performance.now() } });
        this.dispatchEvent(event);
      }, Math.max(0, atMs - performance.now()));
    };
    if (useTactile) {
      timers.tactile = setTimeout(() => {
        try {
          if (this.audioEnabled && this.context.state !== "running") throw new Error("Phone audio was interrupted.");
          const atMs = this.requestVibration([70, 45, 130, 55, 210]);
          finish(atMs + RESPONSE_SETTLE_MS);
          this.dispatchEvent(new CustomEvent("vibration-requested", { detail: { atMs } }));
        } catch (error) {
          this.disarm();
          this.dispatchEvent(new CustomEvent("output-error", { detail: error }));
        }
      }, Math.max(0, startAt + DEMO_TACTILE_MS - performance.now()));
    } else {
      finish(startAt + DEMO_AUDIO_MS);
    }
    return { startAt, useTactile };
  }

  stopDemo() {
    if (this.timeout && typeof this.timeout === "object") {
      clearTimeout(this.timeout.tactile);
      clearTimeout(this.timeout.completed);
    } else {
      clearTimeout(this.timeout);
    }
    this.timeout = null;
    if (this.oscillator) {
      try { this.oscillator.stop(); } catch { /* already stopped */ }
      this.oscillator.disconnect();
      this.oscillator = null;
    }
    this.navigatorObject?.vibrate?.(0);
  }

  disarm() {
    this.armGeneration += 1;
    this.stopDemo();
    this.armed = false;
  }
}
