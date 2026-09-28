# PPS Kit agent entry point

PPS Kit creates, prepares, and replicates peripersonal-space experiments. Its
priority is scientific contracts, reproducibility, native timing, and usable
authoring. Voice cloning and XR/VR are not default work.

The product has one central flow: Designer creates and previews spatial stimuli
through the existing 3DTI/SOFA renderer and 3D viewer, then exports a JSON
experiment profile describing its ingredients, file locations, and assembly
rules. Runner consumes that profile, assembles and executes the experiment,
and records responses and results. Reuse the existing profile, segment, render,
schedule, and execution owners; add no competing planner or command authority.

Read this page and [CURRENT_WORK.md](CURRENT_WORK.md), choose a domain below,
then load only its relevant references and skills. Do not read all of `For-AI/`,
`project_context.md`, or the decision archive before every task.

| Task | Start here |
|---|---|
| Designer controls, layout, segment interaction, browser previews | [Design and UI](domains/design-ui.md) |
| Stimuli, schedules, schemas, execution, response/LSL evidence, Rust/Tauri | [Experiment runtime](domains/experiment-runtime.md) |
| Published paradigms, paper audits, replication claims, analysis, manuscript | [Scientific evidence](domains/scientific-evidence.md) |
| Git checkpoints, tests, Pages, component ownership, installers | [Release operations](domains/release-operations.md) and [packaging](packaging/README.md) |

For cross-domain work, select one owning domain and read the neighboring
handoff contract. [SKILLS.md](SKILLS.md) maps skills to tasks;
[WORKFLOW.md](WORKFLOW.md) separates preview, source, packaging, and release.
[module_map.md](module_map.md) locates code without loading history.

## Shared boundaries

- Product source lives in `apps/`, `packages/`, `distributions/`, `docs/`,
  `third_party/`, and `website/`. `For-AI/` holds development execution,
  validation, research, memory, and experiments; it never enters an installer.
- Designer and Runner ship independently with exactly one compatible Shared
  component. `.pps-profile`, prepared-experiment packages, Segment 0-6
  manifests, and scientific schemas remain stable handoffs.
- Qualified V1 Python/PySide and candidate V2 Rust/Tauri have different evidence
  states. Compilation or demos cannot promote V2 to research acquisition.
- The V2 Windows target is two standalone Tauri applications with bundled local
  HTML interfaces and Rust native authority. Their ordinary workflows must not
  need GitHub Pages or a Pages-to-PC backend connection. The existing V1
  package remains the compatibility path while this target is built and tested.
- WebView controls request narrow native actions. Scientific timing, privileged
  storage, and native participant execution stay with their native authority.
- Keep participant data, recordings, credentials, downloaded papers, generated
  sessions, and private paths out of tracked memory and public assets.
- Designer `apps/designer/frontend/compiled/` and Runner
  `apps/runner/compiled/` are canonical frontend artifacts. Desktop packages
  bundle their own local bytes. When a public Pages surface intentionally shares
  UI, assemble it from the same allowlisted bytes and verify parity separately.
- Preserve `ppskit.qzz.io`, `/`, `/documentation`, `/download`,
  `/experiment-runner/`, and the existing GitHub Pages fallback routes.

Update only the owning domain/current decision when behavior changes. See
[agent_update_protocol.md](agent_update_protocol.md). Detailed former memory is
preserved in [archive/](archive/README.md) for targeted lookup.
