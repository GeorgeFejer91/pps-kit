---
name: agents-inc-accessibility
description: Use when creating or revising HTML controls, keyboard interaction, accessible names, focus behavior, announcements, or WCAG evidence in browser and WebView interfaces.
---

# Agents Inc Accessibility

## When to Use

Apply to touched browser and WebView controls, forms, dialogs, responsive
layouts, and accessibility reviews. Native UI uses its platform accessibility
APIs and the project's native-surface guidance.

## Invocation Notice

- Tell the user when this skill is running: `agents-inc-accessibility`.
  Skip the notice when the user asked for the skill by name or slash command; spelling and spacing need not match.
  A phrase from this skill's own trigger list is not a name — naming the work is not naming the skill.

## Apply to the changed surface

Preserve the project's accessibility target and selected design. Use semantic
HTML controls first. Give controls useful accessible names, associated labels,
keyboard activation, and visible focus. Keep DOM and focus order meaningful.
Use the existing component primitive when it meets the required widget contract.

Keep dialog focus entry, containment for modal content, close behavior, and
restoration coherent. Preserve access when controls resize or move. An accordion
stretch layout must retain names, expanded state, keyboard operation, readable
minimum sizes, and full-value access. Pretext owns text geometry; this skill
owns interaction semantics. Coordinate both in one rendered verification matrix.

Expose validation state and useful status announcements without announcing
every keystroke, frame, or reactive update. Associate errors with their control.
Choose polite versus urgent announcements by consequence. Preserve reduced-motion
preferences and communicate status through more than color.

Read [criteria.md](references/criteria.md) for thresholds and upstream corrections.
Use actual criterion levels and exceptions when stating a WCAG result. A CSS
example or automated audit does not establish complete conformance.

## Evidence and integration

Select applicable keyboard, focus, accessible-name, contrast, zoom, and supported
assistive-technology checks through the project's authorized verification path.
Record the real browser/WebView and tested interaction states. Use existing
test tooling when authorized; identify manual or unrun scope. Preserve current
acceptance gates and evidence ownership.

Read [UPSTREAM.json](UPSTREAM.json) for the reviewed Agents Inc source and the
declared adaptation. Its original notice is retained in [LICENSE](LICENSE).
