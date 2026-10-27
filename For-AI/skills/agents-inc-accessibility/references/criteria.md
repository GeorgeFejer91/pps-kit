# Criteria and scope corrections

Use the project's agreed target. WCAG 2.2 AA is a useful technical target when
none is specified; it is not an automatic legal conclusion.

- [Text contrast, SC 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
  ordinary text uses 4.5:1; qualifying large text uses 3:1. Apply the criterion's
  actual exceptions. Do not shrink text to satisfy a box contract.
- [Focus appearance, SC 2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)
  is AAA. A sample two-pixel outline is not a universal AA requirement. Check
  visible focus, obscuration, non-text contrast, and the applicable target level.
- [HTML label semantics](https://html.spec.whatwg.org/multipage/forms.html#the-label-element)
  allow more than one associated label. Verify the resulting accessible name;
  do not remove valid labels because an example claims only one can work.
- Automated accessibility tools cover a subset of failures. Avoid an unsupported
  fixed percentage. Check keyboard order and meaningful announcements on the
  actual interface. Live regions are used for relevant status changes, not every
  inserted node. Preserve semantic discovery of ordinary content.

These corrections replace blanket claims in the reviewed upstream guide.
They apply together with the project's privacy, native authority, and layout
requirements. Do not add a component library or replace the visual design merely
to use an example from a skill.
