# Accordion stretch layout

Use this optional mode for a bounded, user-resizable panel whose controls should occupy the available width and height without changing their basic order or introducing a panel scrollbar. The compact panel and the expanded panel are the same interface: extra space is distributed **between** meaningful groups and matrix cells. Do not use this mode merely because a page is responsive; ordinary document flow is better for content that should grow vertically.

Read [pretext.md](pretext.md) for the text API and font parity requirements. Pretext measures text; CSS Grid and Flexbox place the controls.

## Geometry contract

1. Define the panel's supported minimum dimensions and name its anchors: usually header at the top, actions at the bottom, and ordered control groups between them. Group a label with its input so stretch never separates a pair. Keep DOM reading and keyboard order aligned with visual order.
2. Give the shell a definite block size and use `grid-template-rows: auto minmax(0, 1fr) auto` (plus any required status row). Put the ordered groups in the flexible middle region. `align-content: space-between` distributes surplus height among groups; a small `gap` is the floor when height contracts. Use `min-width: 0` and `min-height: 0` where Grid/Flex children must shrink.
3. Let width distribute columns and inline gaps with shrinkable tracks (`minmax(0, 1fr)`) or wrapped Flex rows. Reflow at a content-driven breakpoint when one row no longer fits. Preserve the same anchors and group order across the breakpoint.
4. Derive spacing tokens from **both** dimensions, with lower and upper bounds. Use viewport units for a full-window panel; use container query units or a batched `ResizeObserver` for an embedded panel with definite dimensions. Let preferred type depend on the smaller width-derived and height-derived budget, so a wide but short panel does not suddenly acquire tall typography.

```css
.stretch-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  block-size: 100%;
  min-inline-size: 0;
}
.stretch-panel__body {
  display: grid;
  align-content: space-between;
  gap: var(--minimum-group-gap);
  min-block-size: 0;
  min-inline-size: 0;
}
.stretch-panel__choices {
  display: grid;
  grid-template-columns: repeat(var(--column-count), minmax(0, 1fr));
  column-gap: var(--inline-gap);
  row-gap: var(--block-gap);
}
```

These are geometry roles, not mandatory class names or universal numeric tokens. Choose each bound from the app's real controls and minimum window size. At the minimum, all required controls must fit with the minimum readable type and gaps. If they do not, change the arrangement or minimum dimensions; hiding overflow is not a fit strategy.

## Type and no-fit decisions

- After fonts load, use Pretext to check each bounded label at the preferred size: one-line controls need natural-width, line-count, and line-height checks against the **inner** content box. Use the rendered DOM as the final check.
- Derive `widthBudget` and `heightBudget` as font-size candidates from the panel's usable dimensions and product-specific factors. Start each measurement from `clamp(minReadable, min(widthBudget, heightBudget), preferredMax)`, then use Pretext to try the largest candidate that fits every fixed action in its actual track. Reprepare text when the candidate font changes. Recompute from the current dimensions on each resize so type can grow again after an earlier contraction. If no candidate fits, reflow controls or revise the supported minimum; never shrink below the readable floor. Preserve user-enlarged text instead of reducing an explicit accessibility override.
- Give each no-fit result a deliberate path. Reflow ordinary labels when space allows. For an unbounded status or identifier, keep the full value reachable by keyboard and pointer in a detail view. Do not report ellipsis or `overflow: hidden` as a successful text fit.
- Batch resize and content measurements. Cache preparations by text, font, spacing, and locale. If Pretext is unavailable, keep a readable CSS fallback and mark measurement unavailable rather than claiming fit.

## No-scrollbar acceptance

A strict no-scrollbar request means the **requested panel** has no internal scrolling at every supported size. For a full-window panel the page must also not scroll; an embedded panel does not change its host page's scroll policy. Dialogs and overlays may have a separate policy. Check both dimensions independently: minimum width with tall height, minimum height with wide width, both minimum, both expanded, and each breakpoint on both sides. Assert that group spacing grows when height grows, inline separation grows when width grows, and preferred type grows only when both dimensions permit it. Confirm anchors, group order, non-overlap, visible controls, and full-text access.

Inspect `scrollWidth`/`clientWidth` and `scrollHeight`/`clientHeight` on the panel, its shell, and any status region; include the document for a full-window panel. Also inspect control bounds. `overflow: hidden` can conceal broken geometry, so it is never sufficient evidence by itself. Exercise long values, enlarged text, user text-spacing overrides, light/dark themes, and the target browser or WebView. Report the exact tested range and any state that cannot meet the contract.
