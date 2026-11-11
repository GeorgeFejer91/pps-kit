import { RESPONSE_MAX_MS } from "./tap-response.js";

export const DEMO_AUDIO_MS = 3_000;
export const DEMO_TACTILE_MS = 2_300;
export const DEMO_DURATION_MS = DEMO_TACTILE_MS + RESPONSE_MAX_MS;

function audioContextConstructor() {
  return globalThis.AudioContext || globalThis.webkitAudioContext;
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
    this.audioEnabled = Boolean(audioEnabled);
    this.vibrationEnabled = Boolean(vibrationEnabled);
    if (this.audioEnabled) {
      const Constructor = audioContextConstructor();
      if (!Constructor) throw new Error("Web Audio is unavailable on this browser.");
      this.context ??= new Constructor({ latencyHint: "interactive" });
      if (this.context.state === "suspended") await this.context.resume();
      this.master ??= this.context.createGain();
      this.master.gain.value = 0.7;
      this.master.connect(this.context.destination);
    }
    if (this.vibrationEnabled && this.capabilities().vibration) this.navigatorObject.vibrate(30);
    this.armed = true;
  }

  startDemo() {
    if (!this.armed) throw new Error("Arm phone outputs locally before starting the demo.");
    this.stopDemo();
    const startAt = performance.now();
    if (this.audioEnabled && this.context && this.master) {
      const now = this.context.currentTime;
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
    const tactile = useTactile ? setTimeout(() => {
      const atMs = performance.now();
      if (this.navigatorObject.vibrate([70, 45, 130, 55, 210])) {
        this.dispatchEvent(new CustomEvent("vibration-requested", { detail: { atMs } }));
      }
    }, DEMO_TACTILE_MS) : null;
    const finishAt = startAt + (useTactile ? DEMO_DURATION_MS : DEMO_AUDIO_MS);
    const completed = setTimeout(() => {
      this.timeout = null;
      const event = new Event("complete");
      Object.defineProperty(event, "detail", { value: { startAt, endedAt: performance.now() } });
      this.dispatchEvent(event);
    }, Math.max(0, finishAt + 40 - performance.now()));
    this.timeout = { tactile, completed };
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
    this.stopDemo();
    this.armed = false;
  }
}
