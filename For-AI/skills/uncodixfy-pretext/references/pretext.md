# Pretext text geometry for HTML UI

Read this when implementing the required Pretext path from `SKILL.md`. The API and caveats below were checked against upstream `@chenglou/pretext` 0.0.9 on 2026-09-24. Pin the version used by each project and recheck the [README](https://github.com/chenglou/pretext), [changelog](https://github.com/chenglou/pretext/blob/main/CHANGELOG.md), and [platform bug ledger](https://github.com/chenglou/pretext/blob/main/PLATFORM_BUGS.md) before upgrades.

## Match the painted text

Use a named primary font that is actually loaded on every claimed target. Wait for `document.fonts.load()` or `document.fonts.ready` before preparing text; avoid measuring a fallback and painting another face. Keep a single DOM/Pretext typography contract covering full text, canvas font string, CSS font family/weight/style/size, definite line height, numeric letter spacing, whitespace/word-break behavior, language, and direction. Set `<html lang>`; when language changes, call Pretext's `setLocale()` and prepare again. Prepare again when text, face, weight, style, size, letter spacing, whitespace, or word-break mode changes. Resolve CSS `rem`/`em` sizes to CSS pixels. Prefer whole-pixel sizes where browser parity matters.

Keep measured regions within Pretext's supported model: `white-space: normal` or `pre-wrap`, `word-break: normal` or `keep-all`, `overflow-wrap: break-word`, and `line-break: auto`. Pass numeric pixel letter spacing and a definite pixel line height. It does not separately model optical sizing, arbitrary variation features, automatic hyphenation, nested inline DOM, custom kerning/word spacing, Flex/Grid sizing, padding, or SVG/icon width. `system-ui` and `-apple-system` have known Canvas-versus-DOM differences on macOS. Font fallback, fractional pixel sizes, changed page language, and user minimum-font settings can also cause mismatches. A component requiring unsupported text CSS stays browser-verified, without a Pretext accuracy claim.

The runtime needs `Intl.Segmenter`, Canvas 2D measurement, and Unicode property escapes. Bundle the package locally in Tauri and offline sites. If a required capability or font is absent, show a readable CSS/DOM fallback and flag measurement as unavailable; do not silently mark text as fitted.

## Choose the smallest relevant API

| Need | API | Use |
| --- | --- | --- |
| Predict paragraph, row, or card height at a known width | `prepare()` then `layout()` | Cache preparation by text and typography; recompute layout on width change. |
| Fit a single-line control | `prepareWithSegments()`, `measureNaturalWidth()`, and `measureLineStats()` | Require one line; compare natural width with the actual inner width after icons, gaps, insets, and borders. Also check line height against inner height. |
| Check a bounded multiline region | `prepareWithSegments()` then `measureLineStats()` | Compare `lineCount`, `maxLineWidth`, and `lineCount * lineHeight` with the region budget. |
| Get actual line text | `layoutWithLines()` | Use only when line materialization is needed. |
| Find a tighter multiline width | `walkLineRanges()` or `measureLineStats()` | Search widths while preserving the accepted line count, as in the official bubbles demo. |
| Route text beside media/plots | `layoutNextLineRange()` | Give each line its available width; use only when CSS flow cannot express the design. |
| Predict flat inline runs and atomic chips | `@chenglou/pretext/rich-inline` | Use its documented flat items and `extraWidth`; it is not an HTML renderer. |

For a one-line text button, the fit contract is:

```ts
import { measureLineStats, measureNaturalWidth, prepareWithSegments } from '@chenglou/pretext'

const prepared = prepareWithSegments(label, canvasFont, { letterSpacing: letterSpacingPx })
const fits = measureLineStats(prepared, innerTextWidthPx).lineCount === 1
  && measureNaturalWidth(prepared) <= innerTextWidthPx - safetyMarginPx
  && lineHeightPx <= innerTextHeightPx - safetyMarginPx
```

Compute `innerTextWidthPx` from the region's content box, subtracting the icon and group gap. Do not compare the label with the whole button width. With multiline text, call `measureLineStats(prepared, innerTextWidthPx)` and compare the resulting line count and widest line plus line-height budget. Empty strings return zero Pretext lines while an empty DOM block may still occupy one CSS line; account for that when sizing a container.

Pretext does not choose a font size by itself. First try the preferred readable token. If it fails, grow or reflow the region. If a bounded design truly needs type fitting, test a small approved size range, never below the readable minimum, and return an explicit no-fit result when the minimum still fails. If truncation is approved for secondary text, cut at grapheme boundaries with `Intl.Segmenter` or Pretext cursors; `Array.from(text)` splits code points, not all grapheme clusters. Keep the full text reachable by keyboard, touch, and assistive technology.

## Resize and verification

Use known Grid/Flex geometry or a batched `ResizeObserver` result for width changes. Run `prepare()` once per text/style/locale; on width-only resize rerun `layout()` or line stats. Avoid repeatedly reading `clientWidth` or computed style interleaved with writes. A changed candidate font size needs a fresh preparation. Limit caches when many dynamic strings or fonts cycle through the UI.

After exact fonts load, compare Pretext's prediction with a rendered DOM sample at the smallest and largest supported boxes, breakpoints, 320 CSS px reflow, 200% text resize/zoom, long labels, empty text, unbroken IDs/URLs, emoji/combining sequences, CJK, RTL, and supported translations. Also exercise the WCAG text-spacing override (1.5 line height, 0.12em letter spacing, 0.16em word spacing, 2em paragraph spacing): Pretext cannot model all of it, so the rendered layout must absorb it. Do not reduce the user's enlarged type to make a control pass. Check the *page* as well as the text element: `scrollWidth > clientWidth` or `scrollHeight > clientHeight` in a region that should not scroll is a failure. Test the actual Tauri WebView on each claimed OS; desktop Chromium alone does not qualify WebKitGTK or WKWebView. Preserve an explicit safety margin for rounding and platform differences, and investigate any prediction/DOM mismatch rather than masking it with CSS clipping.

## Official examples and limits

- [Demos index](https://chenglou.me/pretext/): accordion height, chat virtualization, masonry cards, rich text, and obstacle-aware layout.
- [Bubbles demo](https://chenglou.me/pretext/bubbles/): find the tightest multiline width that keeps the same line count.
- [Dynamic layout source](https://github.com/chenglou/pretext/blob/main/pages/demos/dynamic-layout.ts): repeated title-size trials and variable-width lines around obstacles.
- [Research log](https://github.com/chenglou/pretext/blob/main/RESEARCH.md): why preparation and arithmetic layout are split, and known font behavior.
- [README caveats](https://github.com/chenglou/pretext#caveats): supported CSS subset, locale/font pitfalls, and runtime requirements.
- [WCAG 2.2 reflow, resize text, and text spacing](https://www.w3.org/TR/WCAG22/): rendered accessibility checks Pretext alone cannot discharge.

The upstream demos establish possible uses, not proof that an application's fonts, strings, breakpoints, or WebViews fit. Those must pass the local rendered check.
