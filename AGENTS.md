# PPS Kit agent instructions

Read [For-AI/README.md](For-AI/README.md) and
[For-AI/CURRENT_WORK.md](For-AI/CURRENT_WORK.md), then select the task's domain.
Do not load the entire memory archive. PPS Kit's primary purpose is creating
and replicating research-grade peripersonal-space experiments.

Use Ponytail/YAGNI: reuse existing code, add only what the task needs, and retain
scientific validation, calibration, accessibility, privacy, and safety boundaries.
[For-AI/SKILLS.md](For-AI/SKILLS.md) maps skills to actual tasks.
Use its [skill nesting rules](For-AI/SKILLS.md#skill-nesting-and-ownership)
and the [delegation protocol](For-AI/WORKFLOW.md#delegation-and-handoffs).

Follow [For-AI/WORKFLOW.md](For-AI/WORKFLOW.md#ui-exploration-and-promotion).
The owner grants standing authorization to deploy completed GitHub Pages UI
changes after local verification. Rebuild the canonical frontend,
push the scoped change to `main`, and verify the deployed UI on ppskit.com before
handoff. Honor explicit requests for preview-only or local-only work. Packaging
and installer validation are separate deliverables.

Commit and push each completed, verified logical checkpoint and before final
handoff, unless the user requests local-only work. Stage exact intended files;
preserve unrelated edits. Never force-push or merge rewritten history automatically.
If blocked, report the exact Git blocker and retain the local work.

Update only the owning domain/current decision under `For-AI/` when durable
behavior changes. Keep participant data, credentials, generated outputs, and
private paths out of tracked memory. Hardware/XR work is conditional on an
explicitly relevant task; preserve the configured device key when it applies.

<!-- for-ai:shared-skills:start -->
## Shared project workflow

At project entry, also read [For-AI/SKILLS.md](For-AI/SKILLS.md) for the required RTK, GSD Core,
and Superpowers baseline, conditional Rust/Tauri/HTML, accessibility,
performance and MobX routes, and Git worktree policy. Preserve this project's
product and evidence contracts; installing guidance does not adopt MobX.

Read the durable project goal and resume its active checklist at session
start. Before ending, update that same state with evidence, blockers, the
next action, and observed Git/publication state. Keep the overall goal open
until its own acceptance criteria pass.
The completion review and multi-agent work packages are linked from
`For-AI/CURRENT_WORK.md`; keep that file as the active checklist owner.
<!-- for-ai:shared-skills:end -->
