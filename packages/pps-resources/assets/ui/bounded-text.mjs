// Shared by Designer and Runner. Keep CSS in charge of layout and user text size.
export function initializeBoundedText(root, pretext, selector = "[data-pretext]") {
  let cache = new WeakMap();
  let locale = "";
  let frame = 0;
  const observed = new Set();
  const resize = new ResizeObserver(refresh);

  function refresh() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(measure);
  }

  function measure() {
    const nextLocale = document.documentElement.lang || "en";
    if (nextLocale !== locale) {
      locale = nextLocale;
      pretext.setLocale(locale);
      cache = new WeakMap();
    }
    const elements = new Set(root.querySelectorAll(selector));
    for (const element of observed) {
      if (!elements.has(element)) { resize.unobserve(element); observed.delete(element); }
    }
    const results = [];
    for (const element of elements) {
      if (!observed.has(element)) { resize.observe(element); observed.add(element); }
      if (!element.clientWidth || !element.getClientRects().length) continue;
      const style = getComputedStyle(element);
      const px = (value) => Number.parseFloat(value) || 0;
      const insetX = px(style.paddingLeft) + px(style.paddingRight);
      const insetY = px(style.paddingTop) + px(style.paddingBottom) + px(style.borderTopWidth) + px(style.borderBottomWidth);
      const width = Math.max(1, element.clientWidth - insetX);
      const size = px(style.fontSize);
      const lineHeight = px(style.lineHeight) || size * 1.5;
      const text = element.textContent || "";
      const font = `${style.fontStyle} ${style.fontWeight} ${size}px ${style.fontFamily}`;
      const key = JSON.stringify([text, font, style.letterSpacing, style.whiteSpace, style.wordBreak, locale]);
      try {
        let entry = cache.get(element);
        if (entry?.key !== key) {
          entry = { key, prepared: pretext.prepareWithSegments(text, font, {
            letterSpacing: px(style.letterSpacing),
            whiteSpace: style.whiteSpace === "pre-wrap" ? "pre-wrap" : "normal",
            wordBreak: style.wordBreak === "keep-all" ? "keep-all" : "normal",
          }) };
          cache.set(element, entry);
        }
        const stats = pretext.measureLineStats(entry.prepared, width);
        const natural = pretext.measureNaturalWidth(entry.prepared);
        // Rich text and user spacing remain DOM verified, without a fit claim.
        const supported = !element.childElementCount && px(style.wordSpacing) === 0
          && ["normal", "pre-wrap"].includes(style.whiteSpace)
          && ["normal", "keep-all"].includes(style.wordBreak)
          && style.overflowWrap !== "anywhere" && style.direction !== "rtl";
        const result = !supported ? "dom-fallback" : stats.maxLineWidth > width + 1 ? "no-fit"
          : natural > width + 1 ? "reflow" : "fit";
        results.push({ element, result, size, lines: stats.lineCount,
          height: Math.ceil(Math.max(1, stats.lineCount) * lineHeight + insetY) });
      } catch {
        results.push({ element, result: "unavailable" });
      }
    }
    // Batch reads above and writes here; width-only changes reuse preparation.
    for (const { element, result, size, lines, height } of results) {
      element.dataset.pretextResult = result;
      if (size) element.dataset.pretextFontSize = String(size);
      if (lines !== undefined) element.dataset.pretextLineCount = String(lines);
      if (height && ["fit", "reflow"].includes(result)) {
        element.style.setProperty("--pretext-min-height", `${height}px`);
      } else element.style.removeProperty("--pretext-min-height");
    }
  }

  const mutation = new MutationObserver(refresh);
  mutation.observe(root, { childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ["hidden", "lang"] });
  window.addEventListener("resize", refresh);
  document.fonts?.addEventListener("loadingdone", refresh);
  Promise.resolve(document.fonts?.ready).then(refresh);
  return { refresh, disconnect() {
    resize.disconnect(); mutation.disconnect(); cancelAnimationFrame(frame);
    window.removeEventListener("resize", refresh);
    document.fonts?.removeEventListener("loadingdone", refresh);
  } };
}
