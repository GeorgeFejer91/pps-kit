---
name: gsd-core-workflow
description: Use milestone-based context and phase management for large, multi-session, or multi-phase software work.
---

# GSD Core-inspired milestone workflow

Use this task-conditional workflow when work spans phases, sessions, or a
large codebase and needs durable state. This local guide summarizes a method;
it is not GSD Core, does not install it, and does not make its commands or
runtime available.

Reference: [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core), reviewed
2026-10-19. Consult the current upstream documentation for exact runtime
behavior or installation.

## Phase loop

1. **Discuss:** capture the milestone's intended outcome, constraints, and
   implementation decisions before planning. Resolve material ambiguity with
   the user; do not reopen settled scope.
2. **Plan:** inspect the existing architecture and evidence, split the work
   into verifiable phases, and make each phase small enough to execute and
   review with the available context and tools.
3. **Execute:** follow the approved phase plan. Parallelize only independent
   tasks when the user, repository instructions, and available tools permit;
   keep one integrator responsible for the combined result.
4. **Verify:** compare the result with the phase acceptance criteria, run the
   applicable checks, investigate failures, and repair before marking the
   phase complete.
5. **Ship:** use the repository's commit, review, release, or publication
   policy. Record concise durable state in its existing `PROJECT.md`,
   `DECISIONS.md`, `WORKFLOW.md`, or handoff owner.

Keep the active task context lean and preserve only decisions, verified state,
and the next actionable step across sessions. Reuse existing control-plane
documents; do not create GSD-specific state trees, phase archives, or status
ledgers unless the project has chosen and installed GSD Core and the task
requires them. When the actual GSD runtime is requested, follow its official
installation path rather than copying upstream command or agent files.
