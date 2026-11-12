import { audioOutputTime } from "./browser-output-engine.js";
import { RESPONSE_MAX_MS, RESPONSE_SETTLE_MS } from "./tap-response.js";

const ID = /^[a-z0-9_]{1,100}$/u;
const HASH = /^[a-f0-9]{64}$/u;
const SUPPORTED_SLOTS = new Set([
  "before_experiment", "before_each_block", "after_each_block", "between_conditions", "after_experiment",
]);

function requirePlan(condition, message) {
  if (!condition) throw new Error(message);
}

function count(value, maximum) {
  return Number.isSafeInteger(value) && value >= 0 && value <= maximum;
}

async function jsonAt(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("This phone study is unavailable.");
  const text = await response.text();
  requirePlan(text.length <= 8 * 1024 * 1024, "The phone study manifest is too large.");
  return JSON.parse(text);
}

export async function phoneStudyCatalog(base) {
  const catalogue = await jsonAt(new URL("index.json", base));
  requirePlan(Array.isArray(catalogue) && catalogue.length <= 100 &&
    catalogue.every((entry) => ID.test(entry.id) && typeof entry.title === "string" && entry.title.length <= 256),
  "The phone study catalogue is invalid.");
  return catalogue;
}

export async function loadPhoneStudy(base, id) {
  requirePlan(ID.test(id), "Unknown study.");
  const folder = new URL(id + "/", base);
  const plan = await jsonAt(new URL("study.json", folder));
  requirePlan(plan.schema === "pps-phone-study.v1" && plan.profile_id === id &&
    typeof plan.title === "string" && plan.title.length <= 256 &&
    Array.isArray(plan.parts) && plan.parts.length > 0 && plan.parts.length <= 32 &&
    plan.clips && typeof plan.clips === "object", "The phone study manifest is invalid.");
  let totalTrials = 0;
  let needsVibration = false;
  for (const [key, clip] of Object.entries(plan.clips)) {
    requirePlan(HASH.test(key) && clip.file === "audio/" + key + ".flac" &&
      HASH.test(clip.sha256) && count(clip.bytes, 64 * 1024 * 1024) && clip.bytes > 0,
    "An audio clip has an invalid inventory entry.");
  }
  for (const part of plan.parts) {
    requirePlan(Array.isArray(part.blocks) && part.blocks.length > 0 && part.blocks.length <= 128 &&
      Array.isArray(part.instructions) && part.instructions.length <= 12, "The study has invalid parts.");
    for (const slot of part.instructions) {
      requirePlan(SUPPORTED_SLOTS.has(slot.slot) && ["delay", "click", "button"].includes(slot.continue_mode) &&
        typeof slot.label === "string" && slot.label.length <= 256 &&
        typeof slot.button_label === "string" && slot.button_label.length <= 80 &&
        Number.isFinite(slot.delay_s) && slot.delay_s >= 0 && slot.delay_s <= 600 &&
        (slot.clip === null || Object.hasOwn(plan.clips, slot.clip)), "The study has an unsupported instruction step.");
    }
    for (const block of part.blocks) {
      const maxSamples = block.sample_rate * 60 * 60;
      requirePlan(count(block.sample_rate, 192_000) && block.sample_rate >= 8_000 &&
        count(block.length_samples, maxSamples) && Array.isArray(block.trials) && block.trials.length > 0 &&
        block.trials.length <= 4096 && typeof block.label === "string" && block.label.length <= 256,
      "The study has invalid blocks.");
      let previousEnd = 0;
      for (const trial of block.trials) {
        requirePlan(count(trial.start_sample, block.length_samples) && count(trial.end_sample, block.length_samples) &&
          trial.start_sample >= previousEnd && trial.start_sample < trial.end_sample &&
          count(trial.response_anchor_sample, block.length_samples) && trial.response_anchor_sample >= trial.start_sample &&
          (trial.audio_onset_sample === null || count(trial.audio_onset_sample, block.length_samples)) &&
          (trial.tactile_onset_sample === null || (trial.tactile_onset_sample === trial.response_anchor_sample &&
            count(trial.tactile_duration_ms, 1000) && trial.tactile_duration_ms > 0)) &&
          (trial.clip === null || Object.hasOwn(plan.clips, trial.clip)) &&
          typeof trial.response_required === "boolean", "The study has invalid trial timings.");
        previousEnd = trial.end_sample;
        needsVibration ||= trial.tactile_onset_sample !== null;
        totalTrials += 1;
      }
    }
  }
  requirePlan(totalTrials <= 8192 && Object.keys(plan.clips).length <= 2048, "The phone study is too large.");
  return { folder, plan, totalTrials, needsVibration };
}

function wait(ms, signal) {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      signal.removeEventListener("abort", cancel);
      resolve();
    }, Math.max(0, ms));
    function cancel() {
      clearTimeout(timeout);
      reject(signal.reason);
    }
    signal.addEventListener("abort", cancel, { once: true });
  });
}

async function waitForAudio(context, time, signal) {
  while (context.state === "running") {
    signal.throwIfAborted();
    const targetMs = audioOutputTime(context, time);
    const remainingMs = targetMs - performance.now();
    if (remainingMs <= 0) return targetMs;
    await wait(Math.min(remainingMs, 1000), signal);
  }
  throw new Error("Phone audio was interrupted.");
}

async function readClip(study, key, context, signal) {
  const info = study.plan.clips[key];
  const response = await fetch(new URL(info.file, study.folder), { signal });
  if (!response.ok) throw new Error("A required study sound could not be loaded.");
  const bytes = await response.arrayBuffer();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (byte) => byte.toString(16).padStart(2, "0")).join("");
  requirePlan(bytes.byteLength === info.bytes && digest === info.sha256, "A study sound failed integrity verification.");
  signal.throwIfAborted();
  const buffer = await context.decodeAudioData(bytes);
  signal.throwIfAborted();
  requirePlan(buffer.numberOfChannels <= 2, "A study sound has an unsupported output layout.");
  return buffer;
}

/** The phone owns the sound clock, tactile dispatch, and trial identity. */
export class PhoneStudyPlayback {
  constructor(output, callbacks) {
    this.output = output;
    this.callbacks = callbacks;
    this.abort = null;
    this.sources = new Set();
    this.gate = null;
    this.results = [];
  }

  continue() {
    this.gate?.();
  }

  stop() {
    this.abort?.abort();
    this.abort = null;
    this.gate = null;
    for (const source of this.sources) {
      source.stop();
      source.disconnect();
    }
    this.sources.clear();
    this.output.navigatorObject?.vibrate?.(0);
  }

  async start(study) {
    this.stop();
    this.results = [];
    this.abort = new AbortController();
    const signal = this.abort.signal;
    let number = 0;
    let wakeLock;
    try {
      wakeLock = await navigator.wakeLock?.request("screen").catch(() => null);
      signal.throwIfAborted();
      for (const [partIndex, part] of study.plan.parts.entries()) {
        if (partIndex === 0) await this.instruction(study, part, "before_experiment", signal);
        else await this.instruction(study, part, "between_conditions", signal);
        for (const block of part.blocks) {
          await this.instruction(study, part, "before_each_block", signal);
          await this.block(study, block, () => ++number, signal);
          await this.instruction(study, part, "after_each_block", signal);
        }
        if (partIndex === study.plan.parts.length - 1) await this.instruction(study, part, "after_experiment", signal);
      }
      signal.throwIfAborted();
      this.callbacks.complete();
    } catch (error) {
      if (!signal.aborted) {
        this.stop();
        this.callbacks.error(error);
      }
    } finally {
      await wakeLock?.release().catch(() => {});
    }
  }

  play(buffer, time) {
    const source = this.output.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.output.master);
    this.sources.add(source);
    source.addEventListener("ended", () => {
      source.disconnect();
      this.sources.delete(source);
    }, { once: true });
    source.start(time);
  }

  async instruction(study, part, name, signal) {
    const slot = part.instructions.find((entry) => entry.slot === name);
    if (!slot) return;
    signal.throwIfAborted();
    this.callbacks.instruction(slot.label);
    if (slot.clip) {
      const buffer = await readClip(study, slot.clip, this.output.context, signal);
      const context = this.output.context;
      const start = context.currentTime + 0.05;
      this.play(buffer, start);
      await waitForAudio(context, start + buffer.duration, signal);
    }
    if (slot.continue_mode === "delay") await wait(slot.delay_s * 1000, signal);
    else {
      await new Promise((resolve, reject) => {
        signal.throwIfAborted();
        const cancel = () => reject(signal.reason);
        signal.addEventListener("abort", cancel, { once: true });
        this.gate = () => {
          signal.removeEventListener("abort", cancel);
          this.gate = null;
          resolve();
        };
        this.callbacks.gate(slot);
      });
    }
  }

  async block(study, block, nextNumber, signal) {
    const context = this.output.context;
    this.callbacks.instruction("Loading " + block.label);
    const buffers = new Map();
    let decodedBytes = 0;
    for (const { clip } of block.trials) {
      if (clip === null || buffers.has(clip)) continue;
      const buffer = await readClip(study, clip, context, signal);
      decodedBytes += buffer.length * buffer.numberOfChannels * 4;
      requirePlan(decodedBytes <= 96 * 1024 * 1024, "This block exceeds the phone audio memory limit.");
      buffers.set(clip, buffer);
    }
    signal.throwIfAborted();
    if (context.state !== "running") throw new Error("Phone audio is suspended.");
    const leadMs = 100;
    const audioZero = context.currentTime + leadMs / 1000;
    const toMs = (samples) => samples * 1000 / block.sample_rate;
    for (const trial of block.trials) {
      if (trial.clip !== null) this.play(buffers.get(trial.clip), audioZero + trial.start_sample / block.sample_rate);
    }
    let responseEndMs = 0;
    let vibrationEndMs = 0;
    const events = [];
    for (const trial of block.trials) {
      const number = nextNumber();
      if (trial.audio_onset_sample !== null && trial.audio_onset_sample < trial.response_anchor_sample) {
        events.push({ trial, number, sample: trial.audio_onset_sample, opensResponse: false });
      }
      events.push({ trial, number, sample: trial.response_anchor_sample, opensResponse: true });
    }
    events.sort((a, b) => a.sample - b.sample);

    for (const { trial, number, sample, opensResponse } of events) {
      const targetMs = await waitForAudio(context, audioZero + sample / block.sample_rate, signal);
      signal.throwIfAborted();
      let anchorMs = opensResponse ? targetMs : null;
      let tactileMs = null;
      let vibrationLatenessMs = null;
      const existingTrial = this.results[number - 1];
      const startMs = existingTrial?.trial_start_ms ?? targetMs - toMs(sample - trial.start_sample);
      if (opensResponse && trial.tactile_onset_sample !== null) {
        if (performance.now() < vibrationEndMs) await wait(vibrationEndMs - performance.now(), signal);
        if (context.state !== "running") throw new Error("Phone audio was interrupted.");
        anchorMs = this.output.requestVibration(trial.tactile_duration_ms);
        vibrationEndMs = anchorMs + trial.tactile_duration_ms;
        tactileMs = Math.round(anchorMs - startMs);
        vibrationLatenessMs = Math.round(anchorMs - targetMs);
      }
      const responseOffsetMs = anchorMs === null ? toMs(trial.response_anchor_sample - trial.start_sample) : anchorMs - startMs;
      const record = {
        number, response_required: trial.response_required,
        duration_ms: Math.ceil(Math.max(toMs(trial.end_sample - trial.start_sample), responseOffsetMs + RESPONSE_MAX_MS)),
        audio_ms: trial.audio_onset_sample === null ? null : Math.round(toMs(trial.audio_onset_sample - trial.start_sample)),
        tactile_ms: tactileMs,
        response_ms: null, rt_ms: null,
      };
      this.results[number - 1] = {
        ...record, trial_start_ms: startMs, response_anchor_ms: anchorMs, vibration_lateness_ms: vibrationLatenessMs,
      };
      this.callbacks.trial(record, startMs, anchorMs, Boolean(existingTrial));
      if (anchorMs !== null) responseEndMs = Math.max(responseEndMs, anchorMs + RESPONSE_SETTLE_MS);
    }
    await waitForAudio(context, audioZero + block.length_samples / block.sample_rate, signal);
    if (responseEndMs > performance.now()) await wait(responseEndMs - performance.now(), signal);
  }
}
