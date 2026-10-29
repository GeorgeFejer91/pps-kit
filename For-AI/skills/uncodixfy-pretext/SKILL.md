---
name: uncodixfy-pretext
description: Design, build, or revise text-bearing HTML interfaces for browsers, phones, and Tauri WebViews using restrained Uncodixfy aesthetics, box-first geometry, and required Pretext measurement. Use when control labels, responsive text, or bounded regions must remain legible through resizing and localization. Includes an optional accordion stretch layout for bounded panels that must adapt to width and height without panel scrollbars. Do not use for native-only UI or canvas-only rendering.
---

# Uncodixfy Pretext

Build an HTML interface whose layout is determined by the job of each region, then fit readable text into those regions with [Cheng Lou's Pretext](https://github.com/chenglou/pretext). The target is zero *unintended* clipping, overlap, or page overflow in the supported viewport, zoom, content, language, and WebView matrix. Pretext predicts text; the rendered browser is the final authority.

This skill keeps [Uncodixfy's](https://github.com/cyxzdev/uncodixfy) resistance to generic decorative UI. Treat its palette, font, radius, and sidebar numbers as examples, not universal bans: several conflict with one another and with real product constraints. Use the product's existing visual language and make decoration earn its space.

## Required companion and scope

- Load the installed `ponytail` skill before implementation. Apply its YAGNI ladder to wrappers, state, dependencies, components, and visual decoration. If it is unavailable, say so and still make the smallest complete change.
- Pretext is the deliberate exception to the no-new-dependency preference: the user requires it for text-bearing HTML UI work. When creating a page or changing its text layout, install a locked `@chenglou/pretext` version and implement actual measurement for its bounded text regions. A name-drop, CSS `clamp()`, or test-only mock does not count. Keep the implementation scoped to the touched page; do not migrate unrelated pages.
- Read [references/pretext.md](references/pretext.md) before choosing the API, fonts, fit behavior, or verification. Recheck the current upstream README and changelog when selecting or upgrading the package.

## Box-first design

1. Map the real content, controls, and states. Give each region a purpose and a content priority. Use semantic HTML and DOM reading order. Remove speculative panels, decorative labels, and redundant wrappers.
2. Allocate the outer layout with Grid/Flex and explicit gaps. Use `box-sizing: border-box`, shrinkable tracks such as `minmax(0, 1fr)`, and `min-width: 0` on text-bearing flex/grid children. Avoid fixed viewport widths that make phone or zoom layouts impossible.
3. Give controls balanced inline and block insets. Center the *content group* of a button both ways with Grid or Flex; an icon plus label is one group with a measured gap. Normalize SVG view boxes when the icon looks off-center. Keep reading text and form labels aligned for scanning; geometric symmetry does not mean centering paragraphs.
4. Define each bounded region's usable content width and height after padding, borders, icons, gaps, badges, and safe-area insets. The box is allocated by its role; Pretext checks a preferred type token and, only when necessary, a small approved range, or tells the layout to grow/reflow. Do not make every box an arbitrary tight frame around its current string.
5. Define an explicit result when text cannot fit: grow, reflow, scroll, reveal the full value, or reject the state. For primary actions, critical status, instructions, and consent, preserve the full text. Never use ellipsis, hidden overflow, or an unreadably small font as an unreported success.

Keep a small type and spacing scale. Preserve readable minimum sizes, contrast, visible focus, input labels, and touch target sizes appropriate to the device. A narrow phone layout may rearrange actions or shorten a noncritical visible label while preserving its accessible name; it should not merely shrink a desktop window.

```css
.action { display: inline-flex; align-items: center; justify-content: center; gap: .5rem; text-align: center; }
.action > svg { display: block; flex: none; }
.action > .label { min-width: 0; }
```

Use the same centering for text-only and icon-only controls. Center the group, then let Pretext evaluate the label's remaining inner space.

## Optional mode: accordion stretch layout

When the user requests an accordion stretch layout, or describes a bounded panel whose control spacing and type should expand and compress with both width and height while preserving group order, read [references/accordion-stretch.md](references/accordion-stretch.md). Apply that mode only to the requested surface; keep the ordinary box-first layout for other pages. Its no-scrollbar contract applies to the bounded panel, with dialogs and overlays handled by their own content policy.

## Pretext decision rule

Use Pretext for every bounded label or text region on the touched UI, including buttons, tabs, compact status cells, dialogs, card summaries, and mobile counterparts. One-line controls require one-line, natural-width, and line-height checks. Multiline regions require line-count, widest-line, and height checks. Keep one typography contract for the DOM and Pretext: full text, loaded font, weight, style, pixel size and line height, numeric letter spacing, whitespace and word-break modes, and locale. Treat a changed font size or locale as a new preparation; a pure width change reuses prepared text for cheap layout.

Prefer allocating more room, wrapping, or a different layout before reducing type. Choose only from a small readable size range, and expose a no-fit state at the minimum. Never counteract user text enlargement by shrinking measured type back down. If the string is unbounded, choose a behavior that keeps the full value accessible. For dynamic UI, batch resize/content updates and keep a bounded cache; avoid DOM read/write loops on every component.

Pretext does not size the CSS box, center SVGs, lay out Grid/Flex, or guarantee the browser's final pixels. Check the actual rendered DOM after fonts load. Do not describe a component as overflow-safe until the supported cases pass that check.

## Handoff gate

Verify the touched UI at its minimum, normal, and maximum widths; phone portrait and landscape when supported; 320 CSS px reflow and 200% text resize/zoom; long real and localized strings; user text-spacing overrides; and the target browser/Tauri WebViews. Check intended text regions and page edges for horizontal and vertical overflow, clipping, overlap, and focus/accessibility regressions. A green Pretext prediction is not a substitute for a rendered check. Report the tested matrix and any unsupported condition. Use the smallest automated check that can fail for the relevant text contract, plus a rendered check.
