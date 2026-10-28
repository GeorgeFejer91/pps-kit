// Shared by Designer and Runner. Keep CSS in charge of layout and user text size.
export function initializeBoundedText(root, pretext, selector = "[data-pretext]") {
  let cache = new WeakMap();
  let locale = "";
  let frame = 0;
  let disposed = false;
  const observed = new Set();
  const writtenStyles = new WeakMap();
  const resize = new ResizeObserver(refresh);

  function refresh() {
    if (disposed || frame) return;
    frame = requestAnimationFrame(() => { frame = 0; measure(); });
  }

  function invalidateFonts() {
    cache = new WeakMap();
    pretext.clearCache?.();
    refresh();
  }

  function measure() {
    const nextLocale = document.documentElement.lang || "en";
    let localeAvailable = true;
    try {
      if (nextLocale !== locale) {
        pretext.setLocale(nextLocale);
        locale = nextLocale;
        cache = new WeakMap();
      }
    } catch { localeAvailable = false; }
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
      const paddingY = px(style.paddingTop) + px(style.paddingBottom);
      const insetY = paddingY + px(style.borderTopWidth) + px(style.borderBottomWidth);
      // clientWidth/Height round to integer CSS pixels. Intrinsic labels may lose
      // a fractional pixel and spuriously wrap; resolved CSS sizes retain it and
      // remain in logical pixels under user zoom (unlike viewport rectangles).
      const resolvedWidth = Number.parseFloat(style.width);
      const resolvedHeight = Number.parseFloat(style.height);
      const borderBox = style.boxSizing === "border-box";
      const width = Math.max(1, Number.isFinite(resolvedWidth)
        ? resolvedWidth - (borderBox ? insetX + px(style.borderLeftWidth) + px(style.borderRightWidth) : 0)
        : element.clientWidth - insetX);
      const innerHeight = Math.max(0, Number.isFinite(resolvedHeight)
        ? resolvedHeight - (borderBox ? insetY : 0) : element.clientHeight - paddingY);
      const size = px(style.fontSize);
      const lineHeight = px(style.lineHeight) || size * 1.5;
      const text = element.textContent || "";
      const font = `${style.fontStyle} ${style.fontWeight} ${size}px ${style.fontFamily}`;
      const key = JSON.stringify([text, font, style.letterSpacing, style.whiteSpace, style.wordBreak, locale]);
      const maxLines = element.dataset.pretextMode === "single-line" ? 1
        : Number.parseInt(element.dataset.pretextMaxLines, 10) || Infinity;
      const domFits = element.scrollWidth <= element.clientWidth + 1
        && element.scrollHeight <= element.clientHeight + 1;
      const common = { element, size, domResult: domFits ? "fit" : "no-fit" };
      try {
        if (!localeAvailable) throw new Error("Text locale unavailable");
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
        const supported = !element.childElementCount && Number.isFinite(Number.parseFloat(style.lineHeight))
          && px(style.wordSpacing) === 0
          && ["normal", "pre-wrap"].includes(style.whiteSpace)
          && ["normal", "keep-all"].includes(style.wordBreak)
          && style.overflowWrap !== "anywhere" && style.direction !== "rtl";
        let renderedLines;
        if (!supported && Number.isFinite(maxLines)) {
          // Text-leaf rectangles avoid counting a rich parent's union box.
          // Inline superscripts/smaller spans share a line when their bands overlap.
          const range = document.createRange();
          const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
          const rectangles = [];
          while (walker.nextNode()) {
            range.selectNodeContents(walker.currentNode);
            rectangles.push(...range.getClientRects());
          }
          const bands = [];
          for (const rect of rectangles.sort((a, b) => a.top - b.top)) {
            if (!rect.width || !rect.height) continue;
            const band = bands.find(item => rect.top < item.bottom - 1 && rect.bottom > item.top + 1);
            if (band) { band.top = Math.min(band.top, rect.top); band.bottom = Math.max(band.bottom, rect.bottom); }
            else bands.push({ top: rect.top, bottom: rect.bottom });
          }
          renderedLines = bands.length;
        }
        const exceedsLines = supported ? stats.lineCount > maxLines : renderedLines > maxLines;
        const predictedOverflow = supported && (stats.maxLineWidth > width + 1
          || Math.max(1, stats.lineCount) * lineHeight > innerHeight + 1
          || (maxLines === 1 && natural > width + 1));
        const result = !domFits || exceedsLines || predictedOverflow ? "no-fit"
          : !supported ? "dom-fallback" : natural > width + 1 ? "reflow" : "fit";
        results.push({ ...common, result, lines: supported ? stats.lineCount : undefined, renderedLines,
          height: Math.ceil(Math.max(1, stats.lineCount) * lineHeight + insetY) });
      } catch {
        results.push({ ...common, result: "unavailable" });
      }
    }
    // Batch reads above and writes here; width-only changes reuse preparation.
    for (const { element, result, domResult, size, lines, renderedLines, height } of results) {
      element.dataset.pretextResult = result;
      element.dataset.pretextDomResult = domResult;
      if (size) element.dataset.pretextFontSize = String(size);
      if (lines !== undefined) element.dataset.pretextLineCount = String(lines);
      else delete element.dataset.pretextLineCount;
      if (renderedLines !== undefined) element.dataset.pretextDomLineCount = String(renderedLines);
      else delete element.dataset.pretextDomLineCount;
      const minimum = height && ["fit", "reflow"].includes(result) ? `${height}px` : "";
      if (element.style.getPropertyValue("--pretext-min-height") !== minimum) {
        if (minimum) element.style.setProperty("--pretext-min-height", minimum);
        else element.style.removeProperty("--pretext-min-height");
        writtenStyles.set(element, element.getAttribute("style"));
      }
    }
  }

  const mutation = new MutationObserver(records => {
    // Ignore only our exact custom-property write; app typography/mode edits refresh.
    const changed = records.some(record => record.attributeName !== "style"
      || record.target.getAttribute("style") !== writtenStyles.get(record.target));
    for (const record of records) if (record.attributeName === "style") writtenStyles.delete(record.target);
    if (changed) refresh();
  });
  mutation.observe(root, { childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ["hidden", "lang", "dir", "class", "style", "open",
      "data-pretext-mode", "data-pretext-max-lines"] });
  // Root typography and locale can change above document.body without resizing it.
  if (root !== document.documentElement) mutation.observe(document.documentElement,
    { attributes: true, attributeFilter: ["lang", "dir", "class", "style"] });
  window.addEventListener("resize", refresh);
  document.fonts?.addEventListener("loadingdone", invalidateFonts);
  Promise.resolve(document.fonts?.ready).then(invalidateFonts);
  return { refresh, disconnect() {
    disposed = true;
    resize.disconnect(); mutation.disconnect(); cancelAnimationFrame(frame);
    window.removeEventListener("resize", refresh);
    document.fonts?.removeEventListener("loadingdone", invalidateFonts);
  } };
}
