# Current direction and decisions

This is a compact decision summary, not an append-only session transcript.
Replace superseded direction here; retain evidence in its owning domain.
Prior decisions remain searchable in [the historical ledger](archive/evolving_goals.md).

## 2026-09-27 — task-scoped research software workflow

- PPS Kit creates and replicates PPS experiments. Scientific contracts,
  reproducibility, native timing, and usable authoring govern scope.
  Voice cloning and XR/VR are not routine project dependencies.
- Designer has two responsibilities: create/preview controllable spatial stimuli
  using the existing renderer and 3D view; export a JSON experiment profile with
  ingredients, file locations, and assembly rules. Runner reads that profile,
  assembles the experiment, owns native execution, and records specified data.
  This is the scope test for simplification and new modules.
- Start with the short entry page/current work record; route to design/UI,
  experiment runtime, scientific evidence, or release operations. Load only
  relevant references and skills. Detailed history is preserved.
- Use Ponytail's smallest-working-change ladder in product code and guidance.
  Reuse existing modules and gates; centralize repeated decisions in their
  current owner. Delete duplicate paths and unused helpers before adding layers.
  Preserve calibration, input validation, accessibility, and evidence boundaries.
- Stage UI work as local preview, verified source promotion, packaging, and
  release. A preview can be complete without an installer. Unsettled designs
  remain on a review branch until the concrete preview is accepted.
- Commit/push each verified logical checkpoint and before final handoff. Keep
  incomplete preview checkpoints off `main`; respect local-only requests.
  No timer or background service commits arbitrary work.
- Preserve V1 Designer/Runner/Shared contracts while V2 develops. Native
  scientific/release evidence is required before retiring compatibility paths
  or describing the candidate as acquisition-ready.

## 2026-09-28 — standalone Windows desktop target

- Package Designer and Runner as locally installed Tauri/Rust applications,
  each with its own bundled HTML/CSS/JavaScript GUI. A Full Windows installer
  installs both entrypoints and one compatible Shared resource set. The V1
  Python packages remain compatibility candidates until the replacement meets
  the installed and scientific gates.
- Rust owns privileged files, experiment state, validation, timing, and native
  integration; the WebViews use narrow typed IPC. The installed workflow runs
  without GitHub Pages or a Pages-hosted frontend connecting to a PC backend.
  Pages remains a separate public information/browser surface, not the
  installed application's UI or backend transport.
- Lay out bounded controls from the available box inward. Establish responsive
  box geometry first, then use Pretext with the rendered font to measure text
  within the inner content box. Prefer wrap, growth, or reflow over shrinking;
  keep readable approved font sizes and user zoom. Verify final DOM geometry
  and the actual Tauri WebView.
- [Packaging guidance](packaging/README.md) owns the installer plan and evidence;
  product assets and generated packages remain outside `For-AI/`.

## Next-work selection

[CURRENT_WORK.md](CURRENT_WORK.md) records the active domain, requested outcome,
stage, evidence, and next gate. A historical backlog item does not authorize
implementation. Select the next task from the user's request and current
contracts, then scope one independently verifiable slice.
