const GENERIC_AUDIO_LABELS = new Set(["Audio box", "Looming Stimulus", "Fixed audio clip", "Audio pool"]);

export function audioBoxLabels(element = {}) {
  const labels = (element.source_labels || []).filter(Boolean);
  if (!labels.length && element.source_label) labels.push(element.source_label);
  const fallback = String(element.label || "").trim();
  if (!labels.length && fallback && !GENERIC_AUDIO_LABELS.has(fallback)) labels.push(fallback);
  return Array.from(new Set(labels));
}

function choices(element) {
  return element.kind === "jitter"
    ? (element.jitter_values_ms || []).filter(value => Number.isFinite(Number(value)))
    : audioBoxLabels(element);
}

// Count factors, never their Cartesian product. Infinity is an explicit UI overflow state.
export function countStripVariants(strip = {}) {
  const elements = strip.elements || [];
  if (!elements.length) return 0;
  let total = 1;
  for (const element of elements) {
    const length = choices(element).length;
    if (!length) return 0;
    total *= length;
    if (!Number.isSafeInteger(total)) total = Infinity;
  }
  return total;
}

export function assertCountLimit(count, limit = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(limit) || limit < 0) throw new RangeError("Invalid sequence limit.");
  if (!Number.isSafeInteger(count)) throw new RangeError("This plan exceeds the safe integer count. Reduce its choices before generating; the draft is preserved.");
  if (count > limit) throw new RangeError(`This plan exceeds the limit of ${limit}. Reduce its choices before generating; the draft is preserved.`);
  return count;
}

export function assertSequenceLimit(strips, limit = Number.MAX_SAFE_INTEGER) {
  return assertCountLimit(strips.reduce((total, strip) => total + countStripVariants(strip), 0), limit);
}

function* orderedVariants(strip, limit) {
  const elements = strip.elements || [];
  const factors = elements.map(element => choices(element).map(value => element.kind === "jitter"
    ? { kind: "jitter", label: `${element.label || "Jitter"} (${value} ms)`, value }
    : { kind: "audio", label: value }));
  if (!factors.length || factors.some(factor => !factor.length)) return;
  const indices = factors.map(() => 0);
  for (let emitted = 0; emitted < limit; emitted++) {
    yield factors.map((factor, index) => factor[indices[index]]);
    let index = indices.length - 1;
    while (index >= 0 && ++indices[index] === factors[index].length) indices[index--] = 0;
    if (index < 0) return;
  }
}

export function iterateStripVariants(strip, limit = Number.MAX_SAFE_INTEGER) {
  const count = assertSequenceLimit([strip], limit);
  return orderedVariants(strip, count);
}

export function previewStripVariants(strip, limit) {
  assertCountLimit(0, limit);
  return Array.from(orderedVariants(strip, limit));
}

export function variantCountLabel(strip) {
  const count = countStripVariants(strip);
  return Number.isFinite(count) ? `${count} ${count === 1 ? "variant" : "variants"}`
    : "Too many variants to count exactly — reduce choices before generating";
}
