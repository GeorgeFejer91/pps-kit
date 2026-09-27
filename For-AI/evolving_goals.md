# Current direction and decisions

This is a compact decision summary, not an append-only session transcript.
Replace superseded direction here; retain evidence in its owning domain.
Prior decisions remain searchable in [the historical ledger](archive/evolving_goals.md).

## 2026-09-27 — task-scoped research software workflow

- PPS Kit creates and replicates PPS experiments. Scientific contracts,
  reproducibility, native timing, and usable authoring govern scope.
  Voice cloning and XR/VR are not routine project dependencies.
- Start with the short entry page/current work record; route to design/UI,
  experiment runtime, scientific evidence, or release operations. Load only
  relevant references and skills. Detailed history is preserved.
- Use Ponytail's smallest-working-change ladder. Reuse existing code and gates;
  add modules only when a concrete ownership seam helps the requested change.
- Stage UI work as local preview, verified source promotion, packaging, and
  release. A preview can be complete without an installer. Unsettled designs
  remain on a review branch until the concrete preview is accepted.
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
