---
name: mobx-integration
description: Use when evaluating MobX adoption, integrating MobX stores into a JavaScript or TypeScript application, or repairing observable state, async updates, or subscription lifetimes in an existing MobX application.
---

# MobX Integration

## When to Use

Use for MobX suitability decisions and incremental integration in web apps,
Tauri WebViews, and game interfaces. Use for stale observable views, async
races, duplicated state, or leaked subscriptions in an existing MobX app.

## When Not to Use

An ordinary UI change with adequate existing state management does not require
MobX. Native Rust, C#, Unity, and engine simulation state retain their owners.

## Invocation Notice

- Tell the user when this skill is running: `mobx-integration`.
  Skip the notice when the user asked for the skill by name or slash command; spelling and spacing need not match.
  A phrase from this skill's own trigger list is not a name — naming the work is not naming the skill.

## Choose the state boundary

Inspect the framework, installed MobX/binding versions, current state owners,
async paths, and target runtimes. Preserve the package manager and lockfile.
Identify the requested outcome before proposing a new dependency.

| Existing situation | Decision |
| --- | --- |
| A few local values; current framework state is sufficient | Keep that state owner |
| Shared mutable application state with several dependent views or derived values | Evaluate MobX against the current solution |
| A server cache, URL router, Rust service, or persistence layer already owns data | Retain that owner; define a view projection and command boundary if needed |
| Per-frame physics, transforms, collision, audio, or rendering state | Keep the engine's hot path; evaluate a bounded UI bridge separately |

State the reason to adopt or retain the current solution, the owned fields,
derived values, lifetime, and observable acceptance result. Use the existing
project plan/checklist. A positive suitability decision is not permission to
migrate unrelated stores or change the framework. Implement adoption when the
current request covers it; otherwise deliver the suitability decision.

## Implement one slice

Read [reactivity.md](references/reactivity.md) before writing MobX code.
Read [surfaces.md](references/surfaces.md) for the affected adapter only.

Start with one store and one consumer. Keep injected services, native handles,
transport clients, and credentials outside the observable graph. Derive values
with pure computeds instead of copying them into more mutable fields. Choose
explicit annotations when inheritance or a precise boundary requires them.

Keep mutation transactions coherent across asynchronous success and failure.
Handle stale responses, cancellation, and disposal using the application's
existing request/operation identity. Give every subscription a lifetime owner.
Return plain, deliberately selected DTOs across IPC and persistence boundaries.

Preserve the existing composition root. Add service injection where a real
boundary needs it. Do not introduce a DI container, root-store hierarchy,
custom Babel transform, event bus, or persistence framework as a prerequisite.

## Evidence and handoff

Read [acceptance.md](references/acceptance.md) to select the focused checks.
Use the project's existing authorized verification workflow. Preserve test
and execution permissions supplied by the user and environment. Record checks
as passed, failed, or not run with the observed reason.

Report the suitability decision, state owners, changed slice, async and cleanup
behavior, measured results, unresolved gaps, and Git state. Update the existing
task owner; keep broader product acceptance open until its own evidence exists.

## Sources

Adapted from Agents Inc's MobX guidance with framework-specific assumptions
removed and primary MobX documentation checked. Read [UPSTREAM.json](UPSTREAM.json)
for provenance and [LICENSE](LICENSE) for the upstream notice.
