# PPS Interface Design Principles

This is the visual and interaction-design contract for PPS desktop applets and their hosted mirrors. It converts general HCI guidance into testable rules for a dense research-software interface. It supplements, rather than replaces, the segment ownership rules in `dashboard_gui_behavior.md` and `segment_registry_contract.md`.

## Evidence Boundary

These are design heuristics and accessibility constraints, not universal laws. Alignment, proximity, consistent spacing, and reduced visual complexity have empirical and professional support, but no single grid or symmetry ratio is optimal for every task. In particular, symmetry is useful for balance; deliberate asymmetry is allowed when it communicates hierarchy. Accidental misalignment, arbitrary spacing, and inconsistent component geometry are defects.

The PPS implementation uses a 4 px base unit and an 8 px primary rhythm. This is an explicit project convention informed by the [USWDS spacing-token system](https://designsystem.digital.gov/design-tokens/spacing-units/), not a claim that 8 px is scientifically unique. The research basis also includes:

- [Apple Human Interface Guidelines: Layout](https://developer.apple.com/design/human-interface-guidelines/layout), which emphasizes grouping, alignment, hierarchy, whitespace, adaptable layout guides, and consistent spacing.
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/), especially reflow, contrast, visible/unobscured focus, descriptive labels, and minimum target sizing.
- [Nielsen Norman Group's usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/), especially consistency, recognition rather than recall, error prevention, visible status, and focused/minimal presentation.
- Harper et al., [Toward a definition of visual complexity as an implicit measure of cognitive load](https://consensus.app/papers/details/0fc5f5e54590532a95791f1fcaf37098/?utm_source=unknown), supporting visual complexity as a meaningful usability/cognitive-load concern.
- Tuchler et al., [The impact of interface alignment structure on aesthetic appreciation and usability rating](https://consensus.app/papers/details/1896c41e9ce052cead63196fd1e6616a/?utm_source=unknown), supporting the effect of horizontal/vertical alignment structure on perceived usability and aesthetics.
- Watzman, [Visual design principles for usable interfaces](https://consensus.app/papers/details/37a8cc6460dc542690c5020276ce2b72/?utm_source=unknown), describing grids, proximity, hierarchy, whitespace, and predictable placement as a reusable interface system.

## Categorical Design Contract

| Category | General principle | PPS application | Required check |
| --- | --- | --- | --- |
| Task structure | Organize around the user's decisions, not internal implementation. | One Segment 0-6 stage per scientific decision family; do not move Runner/acquisition choices into design stages. | Control ownership matches the segment registry and user workflow. |
| Grid and alignment | Use shared vertical meridians, row baselines, and component geometry. | Panel inner edges, segment headings, form rows, cards, and footers use shared layout tokens. Controls in one action row share height and vertical center. | Paired control heights and centers differ by no more than 1 CSS px; common meridians differ by no more than 1 CSS px. |
| Spacing and proximity | Related elements are closer than unrelated groups; whitespace communicates grouping. | Use the 4/8 px token scale. Avoid one-off 5/7/9/10/13/14 px layout gaps unless required by border/optical correction. | Computed primary gaps resolve to project tokens; section gap is greater than within-group gap. |
| Hierarchy and salience | Visual strength follows task importance. | At most one primary action in a local decision row. Titles, status, metadata, warnings, and secondary actions have descending emphasis. | Primary action is immediately identifiable; metadata and warnings do not compete with it unless blocking. |
| Balance | Balance visual weight without forcing false symmetry. | Use stable column ratios and equal padding. Allow asymmetric action columns or previews when priority or content length requires it. | No accidental lopsided padding, orphaned controls, or unexplained empty columns. |
| Consistency | Same meaning uses the same component, label pattern, size, color, and placement. | Shared tokens define control height, panel padding, radius, spacing, focus, and status styles across all applets. | No local component override without a documented semantic reason. |
| Selection controls | A menu should preserve the spatial context of the field that opened it. | Visible single-choice selectors use the shared bounded combobox: its listbox is anchored to and exactly as wide as its trigger, with a viewport-bounded height. Native selects remain the form-state source underneath. | Opened listbox width and leading edge differ from the trigger by no more than 1 CSS px and never create viewport overflow. |
| Typography and scanability | Reading order and text hierarchy should be obvious. | Left-align researcher forms and long text; keep labels close to controls; constrain prose widths; use stable title/label/metadata levels. | No clipped labels, ambiguous association, excessive line length, or centered body copy. |
| Color and contrast | Do not use color alone; preserve readable contrast in all themes. | Status combines text and color; focus is visible; light/dark themes use the same semantic hierarchy. | WCAG-AA automated checks where machine-testable, plus manual light/dark review. |
| Targets and control geometry | Controls must be large enough and separated enough to operate reliably. | Visible interactive targets are at least 24 x 24 CSS px; ordinary PPS form controls share the standard height; compact exceptions remain at least 28 px. | Browser geometry audit reports no undersized visible target or overlap. |
| Feedback and state | Keep system status visible and local to the action. | Saved/unsaved, capability, draft/finalized, validation, and progress states appear consistently without adding generic dashboard clutter. | Mutations provide immediate visible feedback and actionable errors. |
| Read-only inspection | Capability restrictions must not make legitimate content hard to read. | Template/finalized panels retain full text and surface contrast; the global sidebar lock and disabled mutation controls communicate read-only state instead of repeated per-panel pills or whole-panel opacity. Editable drafts may retain per-step review badges for workflow progress. | Scientific decisions remain readily inspectable in light and dark themes. |
| Error prevention and reversibility | Constrain invalid actions before explaining failures. | Immutable/finalized profiles use copy-to-edit; downstream invalidation is explicit; destructive or locking actions require clear intent. | UI prevents invalid direct edits and preserves provenance. |
| Progressive disclosure | Show what is needed now; keep advanced or explanatory detail contextual. | Segment About dialogs, collapsible completed stages, and advanced connection settings reduce persistent clutter. | Core workflow is operable without reading documentation; detail remains discoverable. |
| Responsiveness and reflow | Preserve meaning and operation as space changes. | Grids collapse deliberately at breakpoints; labels remain attached; fixed/sticky surfaces do not obscure focus; no page-level horizontal overflow. | Laptop, desktop, wide, and narrow viewport captures pass clipping/overflow checks. |
| Accessibility | Keyboard, focus, semantics, contrast, and zoom are product requirements. | Semantic labels, logical focus order, 2 px focus ring, target size, contrast, and reflow are maintained in desktop and hosted modes. | Automated checks are combined with keyboard and manual visual inspection; automation alone is insufficient. |

## Segment 0 Layout Contract

- The profile selector and `Start New Custom Design` are one action row. Their rendered heights and vertical centers match.
- The opened profile list is anchored to the selector and has exactly the same width. Long study names wrap inside that width; the menu must never expand to the longest option or the viewport width.
- The action row, information card, and panel heading share the same inner left/right meridians.
- The action column has a stable width at desktop sizes and collapses to a full-width row at narrow sizes.
- The profile card is a compact vertical flow using tokenized gaps: stable profile ID first, then citation, DOI, and optional source provenance. Do not repeat the selected profile title, template/read-only status, asset count, or recreation caveat in the main card; the selector and workflow state already communicate that context, while the caveat belongs in Segment 0 About.
- Profile identity/provenance uses a compact aligned metadata grid. Empty provenance is removed rather than leaving a blank column.
- The primary action is the only filled/high-salience control in Segment 0.
- The independently launched desktop applet does not show the hosted site's top page-navigation/status bar. Its sidebar already owns the full `Peripersonal Space Design Toolkit` identity, mode, compact sun/moon light/dark toggle, and workflow navigation; Segment 0 begins at the top of the desktop workspace. The theme control uses familiar line icons and one sliding selected-state indicator rather than nested contrast swatches or text. Hosted pages retain their page navigation but use the same sidebar theme toggle rather than a text `Dark`/`Light` button.
- Hosted narrow layouts place the page-navigation header before the sidebar in DOM, focus, and visual order. At `760px` or narrower, page tabs receive their own full-width row, status controls wrap below, the page header remains sticky, and segment headings/actions return to static document flow so the header cannot cover them. Phone-width visible labels may shorten to `Experiment` and `Docs`, but accessible names remain complete and every tab label must fit without overlap or horizontal overflow.
- Profile editing state uses one lock illustration above a single switch placed between `View` and `Edit`. The closed/open shackle and switch position must agree; avoid redundant `Mode` headings or repeated textual status chips. The animation respects reduced-motion preferences, and the switch retains explicit accessible state and naming.

## Mandatory Visual Validation Loop

Every visual/layout change must repeat this loop until the criteria pass:

1. State the affected components and measurable criteria before editing.
2. Build the deterministic shared frontend used by both the desktop package and hosted site.
3. Run `python validation_protocols/scripts/run_designer_visual_layout_audit.py` from the repository root. The audit clicks the visible workflow rail and captures every Segment 0-6 stage at multiple viewports, light/dark states, plus the Segment 0/About views; it also records DOM geometry invariants.
4. Inspect the clean screenshots and generated contact sheet, not only the numeric report. Check hierarchy, balance, grouping, clipping, overlap, whitespace, text wrapping, and whether the intended action dominates appropriately.
5. Correct every hard failure and any material visual defect, rebuild, and rerun the audit.
6. Repeat visual inspection after the correction. A first-pass screenshot is evidence collection, not approval.
7. Run functional mouse-click tests and backend/unit tests separately; visual evidence does not replace interaction or scientific validation.
8. Keep generated screenshots and reports under ignored `artifacts/`; do not treat them as participant or scientific evidence.

Hard audit failures include horizontal page overflow, overlapping controls, clipped primary labels, visible targets below 24 x 24 CSS px, Segment 0 paired-control height/center mismatch above 1 px, common-meridian mismatch above 1 px, missing screenshots, or browser console/page errors.

Pixel-diff baselines may be used only in a stable renderer/OS environment. Playwright notes that screenshot rendering varies by OS, browser, fonts, hardware, and settings; geometry invariants plus human/AI review remain required even when image diffs pass. See [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots) and [accessibility testing](https://playwright.dev/docs/accessibility-testing).
