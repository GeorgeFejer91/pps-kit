# PPS Kit agent instructions

Read [For-AI/README.md](For-AI/README.md) and
[For-AI/CURRENT_WORK.md](For-AI/CURRENT_WORK.md), then select the task's domain.
Do not load the entire memory archive. PPS Kit's primary purpose is creating
and replicating research-grade peripersonal-space experiments.

Use Ponytail/YAGNI: reuse existing code, add only what the task needs, and retain
scientific validation, calibration, accessibility, privacy, and safety boundaries.
[For-AI/SKILLS.md](For-AI/SKILLS.md) maps skills to actual tasks.

Follow [For-AI/WORKFLOW.md](For-AI/WORKFLOW.md): local UI preview first, verified
source promotion second, packaging and release as separate deliverables.
Unsettled previews stay local or on a review branch. At UI source promotion,
rebuild the canonical frontend and verify identical local/hosted-facing bytes.
Do not claim the installed application changed until its package is rebuilt and tested.

Commit and push each completed, verified logical checkpoint and before final
handoff, unless the user requests local-only work. Stage exact intended files;
preserve unrelated edits. Never force-push or merge rewritten history automatically.
If blocked, report the exact Git blocker and retain the local work.

Update only the owning domain/current decision under `For-AI/` when durable
behavior changes. Keep participant data, credentials, generated outputs, and
private paths out of tracked memory. Hardware/XR work is conditional on an
explicitly relevant task; preserve the configured device key when it applies.
