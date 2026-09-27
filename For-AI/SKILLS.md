# Task-to-skill routing

Select skills by the task below. Read the selected `SKILL.md` completely and
only its relevant references. Do not load every skill on every task.

| Task | Skills | Scope |
|---|---|---|
| Implementation, refactoring, dependency/tooling decisions | [ponytail](https://github.com/DietrichGebert/ponytail/tree/main/skills/ponytail) | Smallest complete change; reuse before adding. Scientific safeguards remain mandatory. |
| Designer HTML orchestration | [html-dashboard-orchestrator](skills/html-dashboard-orchestrator/SKILL.md) | PPS segment/backend/handoff contracts and local-first UI workflow. |
| HTML/CSS controls, layout, responsive/localized text | [uncodixfy-pretext](https://github.com/GeorgeFejer91/uncodixfy-pretext) | Existing product identity, actual bounded-text measurement, rendered verification. |
| Real browser controls/screenshots | playwright when available; otherwise existing Playwright validation tooling | Actual interaction and visual proof, not API-only checks. |
| Candidate Rust/Tauri core, IPC, persistence, native integration | [tauri-rust-developer](https://github.com/GeorgeFejer91/tauri-rust-developer-skill) | Existing V2 code; does not authorize a broader framework migration. |
| Remote Runner commands/authentication/state/transport | [tauri-browser-remote-control](https://github.com/GeorgeFejer91/tauri-browser-remote-control) | Typed actions through one native authority; keep routing, authorization, and timing evidence distinct. |
| Papers, scientific methods, evidence or replication claims | consensus-mcp | Discover the configured Consensus tools first; follow its fallback/citation rules. |
| Current technical documentation and primary-source lookup | multi-source-web-search | Load current sources when needed; ordinary code edits do not require a literature review. |
| Scientific manuscript/argument work | [academic-writing-style](https://github.com/GeorgeFejer91/academic-writing-style) | Evidence-calibrated scholarly writing, conditional on access to the private skill. |
| Maintaining project skills / installing missing skills | skill-creator / skill-installer | Environment/guidance setup, not a product runtime dependency. |
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

This is reproducible setup provenance, not a claim that every future machine
has these skills. Do not upgrade application dependencies merely to match an
upstream skill. Use pinned project versions and current primary docs.

Voice-cloning, game-development, XR, and Quest skills are not default PPS work.
Load them only for an explicitly relevant task. `for-ai` targets new projects;
this existing repository uses its own router. `zuradio-builder` and
`questionnaire-editor` are scoped to their own applications.
`tauri-remote-app-builder` overlaps the narrower Tauri/remote skills and is not
required to maintain the existing PPS application.
