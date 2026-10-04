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

Use **Ponytail** and **Uncodixfy Pretext** (including its
`references/accordion-stretch.md` mode) for Planner, Runner, and companion
HTML work; use the local orchestrator for Planner work. Review each UI shell,
each Planner Segment 0–6, each Runner tab, each phone mode, and the bounded
panels within them. For each bounded, resizable panel, define its anchors,
minimum width and height, and ordered control groups before fitting text.
Keep labels with inputs. Content that cannot fit at the readable minimum must
reflow or use an explicit host/detail scroll policy; never conceal controls
behind overflow. Use browser automation for actual controls/rendered geometry.
Load **tauri-rust-developer** for desktop WebView/native boundaries and its
security reference when changing IPC or capabilities; add remote-control
guidance for authorization, transport, or state sync.
[SKILLS.md](../SKILLS.md) records sources and availability handling.

The V1 native Designer's `ShellApi` exposes methods to pywebview; keep its window
reference private because pywebview recursively inspects public API fields.
For packaged checks, open the installed `PPSDesigner.exe` window and confirm
its local health endpoint responds. The windowed launcher writes startup errors
to the user's Designer state directory.

## Scoped implementation and completion

Trace the existing control/state/backend flow, then change one requested screen
or segment. Preserve earlier completed segments and their ownership. Do not
rewrite unrelated panels just to introduce a layout wrapper. Reuse
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
The Planner's embedded 3D viewer receives only named trajectory and camera
commands through parent/iframe messages; the parent does not read cross-origin
frame properties in an installed WebView. Segment status badges wrap their full
text under the shared Pretext check. Segment 6 says ready to lock only after
its run setup is ready and the custom review cursor has confirmed Segments 0–5.
Tauri injects the Planner CSP into every bundled HTML page, including the
viewer: keep `frame-src 'self'` and `frame-ancestors 'self'` so only the bundled
Planner page can embed it. The installed WebView audit must see its ready marker.
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

Runner Experiment Control package panel: the desktop shell supports at least
900×620. The package panel remains in host document flow because the ordered
block list can grow; it has no panel scrollbar. Its profile-preparation and
manifest-selection actions form one bounded vertical group below the package
heading and label. Their grid track fills available width, vertical separation
grows only when room permits, and preferred type grows only with both width and
height. Shared Pretext measures both full labels and raises each button's
minimum height for wrapping; the document can scroll when content exceeds the
window. In the 320 px rendered stress case, each verified block row stacks its
label and metadata so enlarged text stays inside the panel. Exact-source remote
browser screenshots verify this compiled layout with a mocked native boundary;
the installed Windows Runner audit also verifies the three tabs at 1028 px after
native package selection, schedule inspection, and PCM preparation. Installed
zoom, long-label, and text-spacing cases remain open.
The participant badge shows **Submitted** after valid setup before a package is
verified, then **Ready** when the package and setup are both ready.
After native Planner profile preparation or manifest selection, Runner refreshes
its authority snapshot before reporting success so the package badge reflects
the adopted package even if an earlier subscription event was delayed.
