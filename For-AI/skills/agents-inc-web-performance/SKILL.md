---
name: agents-inc-web-performance
description: Use when investigating measured browser or WebView loading cost, interaction latency, rendering work, bundle size, memory growth, or performance budgets.
---

# Agents Inc Web Performance

## When to Use

Use for a reported performance problem or an explicit application performance
budget. Apply to browser interfaces and Tauri WebViews with their actual runtime
conditions. Ordinary UI edits do not require a new instrumentation project.

## Invocation Notice

- Tell the user when this skill is running: `agents-inc-web-performance`.
  Skip the notice when the user asked for the skill by name or slash command; spelling and spacing need not match.
  A phrase from this skill's own trigger list is not a name — naming the work is not naming the skill.

## Measure the affected path

Name the user-visible symptom, target runtime/device, representative workload,
and relevant metric. Reuse current profiling and build output. Separate download,
startup, CPU/render work, native IPC, network latency, and memory retention.
Read [measurement.md](references/measurement.md) to select the applicable metrics.

Preserve the project's budget. When none exists, derive a scoped budget from its
target and requirements. Upstream sample bundle limits and row counts are examples.
Prefer the smallest change supported by the measurement: reduce unnecessary
work, narrow a subscription, defer an unused feature, or reduce a costly asset.

For MobX, inspect observed dependencies, consumer granularity, transaction
boundaries, reaction lifetime, and snapshot-copy cost with `mobx-integration`.
For Tauri, retain native authority and measure the actual command/event path.
Pretext remains the owner of readable text and bounded panel geometry. Preserve
existing no-scroll or pagination contracts when optimizing large collections.

Use the project's framework and bundler. Confirm whether React Compiler is
actually enabled before relying on it. Inspect bundler output before blaming
imports or barrel files for tree-shaking failures. Lazy content can be rendered
or streamed by SSR; use the framework's actual behavior.

## Evidence and permissions

Compare the same workload and target before and after through the existing
authorized verification path. Record metric, conditions, samples, result, and
remaining regressions or gaps. Preserve interaction, accessibility, and data
integrity while changing performance. Add production analytics, telemetry,
proxies, paid services, or CI gates only under matching authorization.

Read [UPSTREAM.json](UPSTREAM.json) for reviewed source and adaptations. The
upstream notice is retained in [LICENSE](LICENSE).
