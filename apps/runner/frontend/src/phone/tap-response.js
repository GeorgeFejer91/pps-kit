export const RESPONSE_MIN_MS = 100;
export const RESPONSE_MAX_MS = 2_000;
const TAP_MAX_DURATION_MS = 500;
export const RESPONSE_SETTLE_MS = RESPONSE_MAX_MS + TAP_MAX_DURATION_MS;
const TAP_MAX_TRAVEL_PX = 24;

/** Timestamp the first isolated tap from contact onset, once release validates the gesture. */
export class TapResponseWindow {
  windows = [];
  contacts = new Set();
  candidate = null;

  open(anchorMs, trialNumber = null, { sideChoice = false } = {}) {
    if (!Number.isFinite(anchorMs) || anchorMs < 0) throw new TypeError("Invalid response anchor.");
    if (trialNumber === null) this.close();
    this.windows = this.windows.filter((window) => window.anchorMs + RESPONSE_MAX_MS >= anchorMs);
    this.windows.push({ anchorMs, trialNumber, sideChoice });
  }

  close() {
    this.windows = [];
    this.candidate = null;
  }

  down({ pointerId, timeStamp, clientX, clientY }, side = null) {
    this.contacts.add(pointerId);
    if (this.contacts.size !== 1) {
      this.candidate = null;
      return;
    }
    if (!Number.isFinite(timeStamp)) return;
    // Each tap belongs to the most recent cue whose response window includes contact onset.
    const window = this.windows.findLast(({ anchorMs }) => {
      const elapsed = timeStamp - anchorMs;
      return elapsed >= RESPONSE_MIN_MS && elapsed <= RESPONSE_MAX_MS;
    });
    if (!window || window.answered) return;
    if (window.sideChoice && side !== "left" && side !== "right") return;
    this.candidate = { pointerId, timeStamp, clientX, clientY, window, choice: window.sideChoice ? side : null };
  }

  move({ pointerId, clientX, clientY }) {
    const tap = this.candidate;
    if (tap?.pointerId === pointerId &&
        Math.hypot(clientX - tap.clientX, clientY - tap.clientY) > TAP_MAX_TRAVEL_PX) {
      this.candidate = null;
    }
  }

  cancel({ pointerId }) {
    this.contacts.delete(pointerId);
    if (this.candidate?.pointerId === pointerId) this.candidate = null;
  }

  up(event) {
    this.move(event);
    const tap = this.candidate;
    this.cancel(event);
    if (tap?.pointerId !== event.pointerId) return null;
    const { anchorMs, trialNumber } = tap.window;
    const duration = event.timeStamp - tap.timeStamp;
    if (!Number.isFinite(duration) || duration < 0 || duration > TAP_MAX_DURATION_MS) return null;
    tap.window.answered = true;
    return {
      atMs: tap.timeStamp,
      reactionTimeMs: tap.timeStamp - anchorMs,
      ...(trialNumber === null ? {} : { trialNumber }),
      ...(tap.choice === null ? {} : { choice: tap.choice }),
    };
  }
}
