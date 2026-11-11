import { RESPONSE_MAX_MS } from "./tap-response.js";

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
      this.play(buffer, this.output.context.currentTime);
      await wait(buffer.duration * 1000, signal);
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
    const blockZeroMs = performance.now() + leadMs;
    const toMs = (samples) => samples * 1000 / block.sample_rate;
    for (const trial of block.trials) {
      if (trial.clip !== null) this.play(buffers.get(trial.clip), audioZero + trial.start_sample / block.sample_rate);
    }
    let blockEndMs = blockZeroMs + toMs(block.length_samples);
    const responseOrder = block.trials
      .map((trial) => ({ trial, number: nextNumber() }))
      .sort((a, b) => a.trial.response_anchor_sample - b.trial.response_anchor_sample);
    for (const { trial, number } of responseOrder) {
      const targetMs = blockZeroMs + toMs(trial.response_anchor_sample);
      await wait(targetMs - performance.now(), signal);
      if (context.state !== "running") throw new Error("Phone audio was interrupted.");
      let anchorMs = targetMs;
      if (trial.tactile_onset_sample !== null) {
        anchorMs = performance.now();
        requirePlan(this.output.navigatorObject.vibrate(trial.tactile_duration_ms),
          "The phone refused a scheduled vibration.");
      }
      const startMs = blockZeroMs + toMs(trial.start_sample);
      const tactileMs = trial.tactile_onset_sample === null ? null : Math.round(anchorMs - startMs);
      const record = {
        number, response_required: trial.response_required,
        duration_ms: Math.ceil(Math.max(toMs(trial.end_sample - trial.start_sample), anchorMs - startMs + RESPONSE_MAX_MS)),
        audio_ms: trial.audio_onset_sample === null ? null : Math.round(toMs(trial.audio_onset_sample - trial.start_sample)),
        tactile_ms: tactileMs,
        response_ms: null, rt_ms: null,
      };
      this.results[number - 1] = { ...record, trial_start_ms: startMs, response_anchor_ms: anchorMs };
      this.callbacks.trial(record, startMs, anchorMs);
      blockEndMs = Math.max(blockEndMs, anchorMs + RESPONSE_MAX_MS);
    }
    await wait(blockEndMs - performance.now(), signal);
  }
}
