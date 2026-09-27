# PPS Kit project context

## Purpose and audience

PPS Kit helps researchers create new peripersonal-space protocols and reproduce
reported experiment parameters without editing application code. Designing,
rendering, preparing, executing, and reconstructing an experiment are separate
scientific responsibilities with auditable handoffs.

Research-grade means preserving stimulus/trajectory definitions, SOA anchors,
tactile routes, baseline/catch semantics, response windows, reproducible orders,
asset identity, and evidence needed to reconstruct what actually happened.
Software conformance, physical timing, perception, and observed PPS effects
are distinct claims.

## Current product architecture

- Designer: HTML/JavaScript authoring plus the Python local service under
  `apps/designer/` and `packages/pps-runtime/`.
- V1 Experiment Runner: qualified Python/PySide Windows acquisition and normal
  post-run review under `apps/runner/` and the shared Python runtime.
- Candidate V2 Runner: Rust/Tauri desktop, browser companion, and shared Rust
  crates. Existing contracts and Python differential checks remain compatibility
  evidence. Native output work is in development; this memory cleanup establishes
  no new acquisition or release qualification.
- Shared: approved templates/resources, public docs, dependencies, and licenses.
  Versioned manifests compose Designer, Runner, and exactly one Shared.

Preserve `peripersonal_space_toolkit`, `.pps-profile`, prepared-experiment,
Segment 0-6 manifests, logical resource paths, and current public CLIs. New path
code uses the centralized product/resource/frontend/writable helpers;
`repo_root()` remains a compatibility alias and frozen apps honor `PPS_TOOLKIT_ROOT`.

## Scope and working policy

Primary work is experiment authoring, generation, scheduling, execution,
calibration, reconstruction, analysis, and published-profile fidelity. Existing
phone/Quest experiments remain optional and are read only for a relevant task.
Do not add voice-cloning or immersive-app workflows by default.

Work through [the domain router](README.md). Apply Ponytail/YAGNI to scope
while retaining scientific checks, accessibility, trust-boundary validation,
and hardware calibration. Use local UI previews before source promotion;
package the verified source selected for a packaging task.
[WORKFLOW.md](WORKFLOW.md) defines those stages.

[Historical context](archive/project_context.md) preserves detailed older
feature/evidence notes. Search it by task rather than treating it as a current
startup checklist. Product contracts and current evidence determine support.
