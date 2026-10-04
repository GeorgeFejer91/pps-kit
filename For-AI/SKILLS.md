# Skill inventory and task routing

Select skills by the task below. Read the selected `SKILL.md` completely and
only its relevant references. Do not load every skill on every task.

Load in order: foundation (`ponytail` for code/tooling), task domain,
implementation surface, then verification. Routes below are conditional on
their task; `ponytail` and the named project contracts are required for code
work. Missing external skills use the disclosed existing-tooling fallback
below, never an invented claim that a skill ran.

This table is the maintained skill inventory. At each task boundary, select
only applicable rows, confirm that each selected skill is available, read its
`SKILL.md` and only the references needed for the change, then record any
unavailable skill and the fallback used. Apply Ponytail/YAGNI after tracing the
existing owner: reuse source, contracts, and checks before adding code,
dependencies, guidance files, or parallel UI implementations. Never trim
validation, calibration, accessibility, privacy, or safety to satisfy YAGNI.

| Task | Skills | Scope |
|---|---|---|
| Implementation, refactoring, dependency/tooling decisions | [ponytail](https://github.com/DietrichGebert/ponytail/tree/main/skills/ponytail) | Smallest complete change; reuse before adding. Scientific safeguards remain mandatory. |
| Designer HTML orchestration | [html-dashboard-orchestrator](skills/html-dashboard-orchestrator/SKILL.md) | PPS segment/backend/handoff contracts and local-first UI workflow. |
| Planner, Runner, and companion HTML/CSS controls and text | [uncodixfy-pretext](https://github.com/GeorgeFejer91/uncodixfy-pretext) | Existing product identity; box-first geometry, actual Pretext measurement, rendered verification, and installed-WebView checks for desktop surfaces. Read the [accordion stretch reference](https://github.com/GeorgeFejer91/uncodixfy-pretext/blob/main/references/accordion-stretch.md) for every UI and segment layout. |
| Real browser controls/screenshots | playwright when available; otherwise existing Playwright validation tooling | Actual interaction and visual proof, not API-only checks. |
| Planner and Runner Rust/Tauri core, IPC, persistence, native integration | [tauri-rust-developer](https://github.com/GeorgeFejer91/tauri-rust-developer-skill) | Primary GitHub-sourced Tauri skill for both V2 apps; read the relevant security, desktop, persistence, latency, verification, and release references. No broader framework migration. |
| Standalone Windows HTML apps and installer packaging | ponytail + tauri-rust-developer + uncodixfy-pretext | Bundle the local UI; use narrow typed Rust IPC; apply accordion stretch to each bounded UI/segment; verify Pretext, installed WebViews, and package inventory. See [packaging](packaging/README.md). |
| Remote Runner commands/authentication/state/transport | [tauri-browser-remote-control](https://github.com/GeorgeFejer91/tauri-browser-remote-control) | Typed actions through one native authority; keep routing, authorization, and timing evidence distinct. |
| Papers, scientific methods, evidence or replication claims | consensus-mcp | Discover the configured Consensus tools first; follow its fallback/citation rules. |
| Current technical documentation and primary-source lookup | multi-source-web-search | Load current sources when needed; ordinary code edits do not require a literature review. |
| Scientific manuscript/argument work | [academic-writing-style](https://github.com/GeorgeFejer91/academic-writing-style) | Evidence-calibrated scholarly writing, conditional on access to the private skill. |
| Maintaining project skills / installing missing skills | skill-creator / skill-installer | Environment/guidance setup, not a product runtime dependency. |
| Explicit agent-guidance conformity review / starting a separate repository | [for-ai](https://github.com/GeorgeFejer91/for-ai-skill) | Apply progressive loading, product/control-plane boundaries, evidence gates, and safe Git rules. Preserve PPS's existing `For-AI/` names and domain owners; bootstrap only fresh repositories. |
| PDF, Word, spreadsheet artifact work | matching pdf/documents/spreadsheets skill | Only for the requested artifact format. |

## Availability and provenance

Discover the active skill catalog first. Local user skills normally reside in
`$CODEX_HOME/skills/` (default `~/.codex/skills/`); the project orchestrator is
tracked above. If an installed skill is absent from this turn's catalog, read
its local file explicitly. New installs are discoverable on the next turn.
If unavailable, report the gap and use the existing domain/check tooling;
do not invent the missing skill's instructions or claim it ran. Install or
upgrade only within the user's setup request, preserving existing local edits.

PC setup on 2026-09-27 installed these source snapshots:

| Skill | Source commit |
|---|---|
| ponytail | `e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156` |
| uncodixfy-pretext | `a02725f87f281d3dc597478c8aa74517a2ebf320` |
| tauri-rust-developer | `4190cdb58899be1138e891f3b5be29da5d92515b` |
| tauri-browser-remote-control | `f7825df1d1bc2c0bae4b9fc4ea602c7ab97ff7ee` |
| for-ai | `30dd44472d5c7053a6da8994352cca1a99d80265` |

This is reproducible setup provenance, not a claim that every future machine
has these skills. Do not upgrade application dependencies merely to match an
upstream skill. Use pinned project versions and current primary docs.

For desktop HTML work, apply both Tauri and Uncodixfy Pretext guidance. Tauri
defines the local native/WebView trust boundary; Pretext measures bounded text
after responsive boxes, padding, icons, and gaps are known. A Pages-hosted
client-to-PC backend is not the desktop packaging architecture. Load the remote
skill only for a separately scoped remote-control feature.

For UI work, review both the whole UI shell and every segment inside it against
Uncodixfy Pretext's `references/accordion-stretch.md`. Apply accordion stretch
to bounded, resizable panels; retain ordinary document flow where content needs
to grow. Record the layout decision for each touched surface before editing:
supported minimum width/height, top/bottom anchors, ordered control groups,
spacing in both dimensions, Pretext-measured labels, and the full-text no-fit
path. A panel that cannot fit at its readable minimum must reflow or use an
explicit host/detail scroll policy; hidden overflow does not count as a fit.

| UI shell | Segments to review separately |
|---|---|
| Experiment Planner desktop and intentionally shared hosted UI | Shell, navigation/workspace, each Segment 0–6, and each bounded panel within the active segment. |
| Experiment Runner desktop | Shell, each Experiment Control/Data Logging/Phone Remote tab, and each bounded panel within the active tab. |
| Runner phone companion | Shell, Controller and Phone Experiment modes, and each bounded panel or disclosure within the active mode. |

Implement and verify one owning segment at a time, then check its shell and the
full UI. Installed-WebView evidence is required for an installed desktop claim.

Voice-cloning, game-development, XR, and Quest skills are not default PPS work.
Load them only for an explicitly relevant task. `for-ai` targets new projects;
this existing repository uses its own router. `zuradio-builder` and
`questionnaire-editor` are scoped to their own applications.
`tauri-remote-app-builder` overlaps the narrower Tauri/remote skills and is not
required to maintain the existing PPS application.
