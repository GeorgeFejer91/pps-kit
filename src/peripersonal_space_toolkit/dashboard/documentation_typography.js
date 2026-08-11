import { layout, prepare } from "@chenglou/pretext";

const DOCUMENTATION_ROOT_SELECTOR = "#documentation-page";
const FIT_SELECTOR = "[data-pretext-fit]";
const DEFAULT_FONT_STACK = '"Aptos", "Noto Sans", "Helvetica Neue", sans-serif';

let resizeObserver = null;
let observedWidth = -1;
let layoutFrame = 0;

function normalizedText(element) {
  return String(element?.textContent || "").replace(/\s+/g, " ").trim();
}

function numericStyle(value, fallback = 0) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function fontForSize(style, size) {
  const fontStyle = style.fontStyle && style.fontStyle !== "normal" ? `${style.fontStyle} ` : "";
  const fontWeight = style.fontWeight && style.fontWeight !== "normal" ? `${style.fontWeight} ` : "";
  return `${fontStyle}${fontWeight}${size}px ${style.fontFamily || DEFAULT_FONT_STACK}`;
}

function measureAtSize(element, text, width, size, lineHeightRatio) {
  const style = getComputedStyle(element);
  const letterSpacing = numericStyle(style.letterSpacing, 0);
  const lineHeight = size * lineHeightRatio;
  const prepared = prepare(text, fontForSize(style, size), { letterSpacing });
  return {
    ...layout(prepared, width, lineHeight),
    lineHeight,
  };
}

function findLargestFit(element, { width, maxHeight = Infinity, maxLines = Infinity, minSize, maxSize }) {
  const text = normalizedText(element);
  if (!text || width <= 0) return null;

  const style = getComputedStyle(element);
  const currentSize = numericStyle(style.fontSize, minSize);
  const currentLineHeight = numericStyle(style.lineHeight, currentSize * 1.5);
  const lineHeightRatio = currentLineHeight / currentSize;
  let low = minSize;
  let high = maxSize;
  let best = minSize;
  let bestMeasurement = measureAtSize(element, text, width, minSize, lineHeightRatio);

  for (let iteration = 0; iteration < 8; iteration += 1) {
    const size = (low + high) / 2;
    const measurement = measureAtSize(element, text, width, size, lineHeightRatio);
    const fits = measurement.height <= maxHeight + 0.5 && measurement.lineCount <= maxLines;
    if (fits) {
      best = size;
      bestMeasurement = measurement;
      low = size;
    } else {
      high = size;
    }
  }

  return {
    size: Math.round(best * 4) / 4,
    lineHeight: Math.round(bestMeasurement.lineHeight * 4) / 4,
    lineCount: bestMeasurement.lineCount,
  };
}

function clearFit(element) {
  element.style.removeProperty("--pretext-font-size");
  element.style.removeProperty("--pretext-line-height");
  delete element.dataset.pretextFontSize;
  delete element.dataset.pretextLineCount;
}

function fitLineBudget(element) {
  const minWidth = Number(element.dataset.pretextMinWidth || 0);
  const width = element.clientWidth;
  if (width < minWidth) {
    clearFit(element);
    return;
  }

  const result = findLargestFit(element, {
    width,
    maxLines: Number(element.dataset.pretextMaxLines || Infinity),
    minSize: Number(element.dataset.pretextMinSize || 16),
    maxSize: Number(element.dataset.pretextMaxSize || 19),
  });
  if (result) applyFit(element, result);
}

function fitMediaHeight(element) {
  const layoutRoot = element.closest(".pps-intro-layout");
  const media = layoutRoot?.querySelector(".pps-intro-media");
  const copy = element.closest(".pps-intro-copy");
  if (!layoutRoot || !media || !copy) return;

  const columns = getComputedStyle(layoutRoot).gridTemplateColumns.split(/\s+/).filter(Boolean);
  if (columns.length < 2) {
    clearFit(element);
    return;
  }

  const mediaRect = media.getBoundingClientRect();
  const copyRect = copy.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const occupiedAbove = Math.max(0, elementRect.top - copyRect.top);
  const availableHeight = Math.max(0, mediaRect.height - occupiedAbove);
  const result = findLargestFit(element, {
    width: element.clientWidth,
    maxHeight: availableHeight,
    minSize: Number(element.dataset.pretextMinSize || 15),
    maxSize: Number(element.dataset.pretextMaxSize || 18),
  });
  if (result) applyFit(element, result);
}

function applyFit(element, result) {
  element.style.setProperty("--pretext-font-size", `${result.size}px`);
  element.style.setProperty("--pretext-line-height", `${result.lineHeight}px`);
  element.dataset.pretextFontSize = String(result.size);
  element.dataset.pretextLineCount = String(result.lineCount);
}

function runDocumentationTypography() {
  const root = document.querySelector(DOCUMENTATION_ROOT_SELECTOR);
  if (!root || root.hidden || root.getBoundingClientRect().width <= 0) return;

  try {
    for (const element of root.querySelectorAll(FIT_SELECTOR)) {
      if (element.dataset.pretextFit === "media-height") fitMediaHeight(element);
      else fitLineBudget(element);
    }
    root.dataset.pretextStatus = "ready";
  } catch (error) {
    for (const element of root.querySelectorAll(FIT_SELECTOR)) clearFit(element);
    root.dataset.pretextStatus = "fallback";
    console.warn("Pretext documentation sizing fell back to CSS typography.", error);
  }
}

export function refreshDocumentationTypography() {
  cancelAnimationFrame(layoutFrame);
  layoutFrame = requestAnimationFrame(() => {
    layoutFrame = requestAnimationFrame(runDocumentationTypography);
  });
}

export function initializeDocumentationTypography() {
  const root = document.querySelector(DOCUMENTATION_ROOT_SELECTOR);
  if (!root) return;

  resizeObserver?.disconnect();
  resizeObserver = new ResizeObserver(([entry]) => {
    const width = entry?.contentRect?.width || 0;
    if (Math.abs(width - observedWidth) < 0.5) return;
    observedWidth = width;
    refreshDocumentationTypography();
  });
  resizeObserver.observe(root);

  if (document.fonts?.ready) {
    document.fonts.ready.then(refreshDocumentationTypography);
  } else {
    refreshDocumentationTypography();
  }
}
