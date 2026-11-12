# Current direction and decisions

This is a compact decision summary, not an append-only session transcript.
Replace superseded direction here; retain evidence in its owning domain.
Prior decisions remain searchable in [the historical ledger](archive/evolving_goals.md).

## 2026-11-10 — two ways to use PPS Kit

| Goal | Acceptance evidence |
| --- | --- |
| **Browser PWA: study preview.** Recreate and preview supported studies using approved premade assets. | In a clean browser with no PPS Kit desktop process, open a public study, assemble it through the existing profile rules, and preview its stimuli and sequence. Verify installation and a cached revisit with the first supported study after initial load. The preview never requires a local companion, a backend URL, or a mutation token. Label it as a preview so browser playback is not mistaken for qualified acquisition. |
| **Windows: Experiment Planner, Experiment Runner, or Experiment Planner + Runner Suite.** The suite uses one installer for both tools. | On a clean supported machine, install both entrypoints with one compatible Shared payload. With the network disconnected, generate a stimulus for a supported study from local inputs, inspect and validate the plan, export its profile, import it in Runner, and complete a supported experiment with inspectable results. Prove the path can generate a study-backed stimulus type beyond the browser's premade choices. |
| **Browser Experiment Runner.** Run prepared audio and vibration studies in Android Chrome. | On the phone, prepare a compatible pack, arm the outputs, run a complete study, and download its trial log. Verify the same participant flow with an optional paired browser for operator control and cue monitoring. Confirm physical audio and vibration on a named phone. Measure their onsets separately before making timing claims. |
| **UI refresh.** Make the two paths and their capabilities clear where people start. | In the browser preview, replace the pictured Local Companion status, URL, token and Connect controls with a clear study choice and an explanation of what the download adds. In the installed suite, expose plan, generate, validate/export and run as the normal path. Check real controls, keyboard/focus, and readable layout at supported widths and zoom before promoting source. |

**Reuse:** Experiment Planner is the existing Designer role. Reuse its renderer,
the Segment 0–6 rules, the verified profile/package handoff and native Runner
authority. The public preview uses assets cleared for redistribution. The
offline suite keeps experiment data and stimulus generation local. V1 remains
a compatibility path; existing optional remote routes are outside the default
journey and retain their own evidence gates when advertised. Reuse the current
Full component composition; select the packaging mechanism when testing the
first supported install. No new hub, transport, or generic stimulus framework
is required by this decision.

[CURRENT_WORK.md](CURRENT_WORK.md) owns the checklist. The existing
[completion review](engineering/validation/docs/completion-review-2026-10-27.md)
owns native work packages and validation gates. Its separation of source,
installed operation, physical timing, perception and behavioral replication
still applies. Qualification remains specific to the supported profiles,
platforms and routes; release remains a separate stage.

## 2026-09-27 — task-scoped research software workflow

- PPS Kit creates and replicates PPS experiments. Scientific contracts,
  reproducibility, native timing, and usable authoring govern scope.
  Voice cloning and XR/VR are not routine project dependencies.
- Start with the short entry page/current work record; route to design/UI,
  experiment runtime, scientific evidence, or release operations. Load only
  relevant references and skills. Detailed history is preserved.
- Use Ponytail's smallest-working-change ladder in product code and guidance.
  Reuse existing modules and gates; centralize repeated decisions in their
  current owner. Delete duplicate paths and unused helpers before adding layers.
  Preserve calibration, input validation, accessibility, and evidence boundaries.
- Verify UI changes locally. For completed Pages UI tasks, use the
  [standing deployment workflow](WORKFLOW.md#ui-exploration-and-promotion) to
  promote the verified change and check ppskit.com before handoff. Packaging
  and release remain separate stages.
- Commit/push each verified logical checkpoint and before final handoff. Keep
  incomplete preview checkpoints off `main`; respect local-only requests.
  No timer or background service commits arbitrary work.
- Preserve V1 Designer/Runner/Shared contracts while V2 develops. Native
  scientific/release evidence is required before retiring compatibility paths
  or describing the candidate as acquisition-ready.

## Next-work selection

[CURRENT_WORK.md](CURRENT_WORK.md) records the active domain, requested outcome,
stage, evidence, and next gate. A historical backlog item does not authorize
implementation. Select the next task from the user's request and current
contracts, then scope one independently verifiable slice.
