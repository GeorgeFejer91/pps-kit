import * as pretext from "@chenglou/pretext";
import { initializeBoundedText } from "../../../packages/pps-resources/assets/ui/bounded-text.mjs";

let typography;
let workflowLabelSizingInitialized = false;

export function refreshDocumentationTypography() { typography?.refresh(); }

export function initializeDocumentationTypography() {
  typography?.disconnect();
  // The shared owner uses ResizeObserver and preserves the computed text size.
  typography = initializeBoundedText(document.body, pretext, [
    "[data-pretext-fit]", "[data-pretext]",
    ".segment-heading > :is(h2, .segment-info-button, .segment-reopen-button)",
    ".stimulus-editor-grid :is(button, .field-row label, legend, .audio-source-file-status, .source-mode-row > span, .source-mode-widget-copy > *, .fixed-clip-trajectory-note, .decision-note)",
    "#schedule-segment button", "#schedule-segment .status-label", "#schedule-segment td",
    "#run-segment button", "#run-segment .status-label", "#run-segment td",
  ].join(","));
  if (!workflowLabelSizingInitialized) {
    workflowLabelSizingInitialized = true;
    initializeWorkflowLabelSizing();
  }
}

function initializeWorkflowLabelSizing() {
  const labels = [...document.querySelectorAll("#toolkit-workflow-nav a > span")];
  const phone = window.matchMedia("(max-width: 760px)");
  const cache = new WeakMap();
  const px = (value) => Number.parseFloat(value) || 0;
  let locale;
  let frame = 0;

  function fit(label) {
    const tile = label.parentElement;
    const style = getComputedStyle(label);
    const box = getComputedStyle(tile);
    const preferred = px(box.fontSize);
    const size = px(style.fontSize);
    const lineRatio = px(style.lineHeight) / size;
    if (preferred > 14 || size > preferred || px(style.wordSpacing) || px(style.letterSpacing)
        || lineRatio > 1.3 || style.direction === "rtl") {
      return { label, result: "dom-fallback" };
    }

    const width = label.clientWidth - 1;
    const height = px(box.minHeight) - px(box.paddingTop) - px(box.paddingBottom)
      - px(box.borderTopWidth) - px(box.borderBottomWidth) - px(box.rowGap)
      - tile.querySelector(".decision-state").offsetHeight;
    const text = label.textContent;
    const font = `${style.fontStyle} ${style.fontWeight}`;
    const key = JSON.stringify([text, font, style.fontFamily, preferred, locale]);
    try {
      let entry = cache.get(label);
      if (entry?.key !== key) {
        const sizes = [preferred, ...[13, 12].filter((candidate) => candidate < preferred)];
        entry = {
          key,
          sizes: sizes.map((candidate) => {
            const prepared = pretext.prepareWithSegments(text, `${font} ${candidate}px ${style.fontFamily}`);
            return { candidate, prepared, width: pretext.measureNaturalWidth(prepared) };
          }),
        };
        cache.set(label, entry);
      }
      const singleLine = entry.sizes.find(({ candidate, prepared, width: natural }) =>
        natural <= width && candidate * lineRatio <= height
        && pretext.measureLineStats(prepared, width).lineCount === 1);
      if (singleLine) return { label, result: "fit", scale: singleLine.candidate / preferred };

      const twoLines = entry.sizes.find(({ candidate, prepared }) => {
        const stats = pretext.measureLineStats(prepared, width);
        return stats.lineCount <= 2 && stats.maxLineWidth <= width
          && stats.lineCount * candidate * lineRatio <= height + preferred * lineRatio;
      });
      return { label, result: "reflow", scale: twoLines ? twoLines.candidate / preferred : 1 };
    } catch {
      return { label, result: "unavailable" };
    }
  }

  function refresh() {
    if (frame || !phone.matches) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (!phone.matches) return;
      const language = document.documentElement.lang || "en";
      if (locale !== language) {
        locale = language;
        pretext.setLocale(locale);
      }
      const results = labels.filter((label) => label.clientWidth > 0).map(fit);
      for (const { label, result, scale } of results) {
        label.dataset.pretextResult = result;
        if (scale && scale < 1) label.style.setProperty("--workflow-label-size", `${scale}em`);
        else label.style.removeProperty("--workflow-label-size");
      }
    });
  }

  document.fonts.ready.then(() => {
    const resize = new ResizeObserver(refresh);
    const changes = new MutationObserver(refresh);
    changes.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    for (const label of labels) {
      resize.observe(label);
      changes.observe(label, { childList: true, characterData: true, subtree: true });
    }
    document.fonts.addEventListener("loadingdone", refresh);
    phone.addEventListener("change", refresh);
    refresh();
  });
}
