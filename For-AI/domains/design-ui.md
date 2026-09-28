# Design and UI

Own Designer/Runner presentation, interaction, and the local preview. Keep
generation, validity, privileged files, and native timing in the backend.
Start with [the module map](../module_map.md) and the requested segment/screen;
a spacing-only change does not require the experiment literature.

## Read for the task

- Designer behavior: relevant headings in
  [dashboard_gui_behavior.md](../dashboard_gui_behavior.md) and
  [segment_registry_contract.md](../segment_registry_contract.md).
- Layout/typography: [interface principles](../interface_design_principles.md).
- Designer orchestration: [the local skill](../skills/html-dashboard-orchestrator/SKILL.md).
- Saved schema/native action: [runtime](experiment-runtime.md).
- Promotion/Pages/installer: [WORKFLOW.md](../WORKFLOW.md) and
  [packaging](../packaging/README.md).

Use **Ponytail**, **Uncodixfy Pretext**, and the local orchestrator for Designer
HTML work. Use browser automation for actual controls/rendered geometry.
Load Tauri/Rust when changing that native boundary; add remote-control guidance
for authorization, transport, or state sync. [SKILLS.md](../SKILLS.md) records
sources and availability handling.

The V1 native Designer's `ShellApi` exposes methods to pywebview; keep its window
reference private because pywebview recursively inspects public API fields.
For packaged checks, open the installed `PPSDesigner.exe` window and confirm
its local health endpoint responds. The windowed launcher writes startup errors
to the user's Designer state directory.

## Scoped implementation and completion

Trace the existing control/state/backend flow, then change one requested screen
or segment. Preserve earlier completed segments and their ownership. Reuse
the installed Pretext typography contract; measure touched bounded labels and
inspect rendered DOM at relevant widths, zoom, and long-string states.

Build canonical assets and exercise real controls locally. Save inspected
screenshots under ignored `artifacts/`; check clipping, overlap, focus,
disabled/read-only behavior, and relevant errors. Use silent isolated browser
sessions unless a visible test is requested.

For exploration, present the working local preview and remain at
**local-preview** until accepted. Preview completion does not start packaging.
At source promotion, check the desktop build uses the canonical compiled bytes.
Check Pages parity when the same change is published there.

The final planner action exports the verified local experiment JSON; the portable
audio bundle remains a separate action. Keep review evidence, instruction audio,
and long source filenames in disclosures so the approved plan remains readable.
Designer and Runner share `pps-resources/assets/ui/bounded-text.mjs` for Pretext
measurement. For each touched bounded control, first set its responsive outer
box with Grid/Flex and `box-sizing`, then subtract padding, borders, icons and
gaps to obtain the inner text box. Use the actual loaded font and matching DOM
typography in Pretext to check candidate labels at approved readable sizes.
CSS owns the final wrap and geometry; measurement informs the size choice. Grow
or reflow the box when text cannot fit without making it hard to read. Never
silently clip critical controls or reduce user zoom. Confirm the final rendered
DOM at relevant widths, zoom, long/localized text and spacing overrides, then
check the actual Tauri WebView for a desktop packaging claim.
