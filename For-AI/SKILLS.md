# Task-to-skill routing

Select skills by the task below. Read the selected `SKILL.md` completely and
only its relevant references. Do not load every skill on every task.

Load in order: foundation (`ponytail` for code/tooling), task domain,
implementation surface, then verification. Routes below are conditional on
their task; `ponytail` and the named project contracts are required for code
work. Missing external skills use the disclosed existing-tooling fallback
below, never an invented claim that a skill ran.

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

Voice-cloning, game-development, XR, and Quest skills are not default PPS work.
Load them only for an explicitly relevant task. `for-ai` targets new projects;
this existing repository uses its own router. `zuradio-builder` and
`questionnaire-editor` are scoped to their own applications.
`tauri-remote-app-builder` overlaps the narrower Tauri/remote skills and is not
required to maintain the existing PPS application.

<!-- for-ai:shared-skills:start -->
## Shared project skill baseline

Apply this baseline in every project. Read the installed `for-ai` skill's
`references/skill-composition.md` for complete overlap and ownership rules.
Load only the selected skill bodies and task references.

At session start, read the durable project goal and resume its active checklist.
Use GSD `.planning/STATE.md`, `ROADMAP.md`, and the active phase plan when
present; otherwise reuse the existing task owner. Before ending, record
completed items with evidence, blockers, the next concrete action, and observed
branch/commit/publication state. Keep the overall goal open until its own
acceptance criteria pass. Do not create a duplicate progress ledger.

| Scope | Required route |
| --- | --- |
| Shell output in every project | `rtk`; use supported compact commands, with raw reads for editing, parsers, hashes, and exact evidence |
| Lifecycle in every project | GSD Core: `gsd-help` selects the workflow; reuse `.planning/` state when present; apply its bounded outcome/evidence discipline inline for small changes |
| Engineering in every project | `superpowers-using-superpowers` selects relevant `superpowers-*` practices; preserve similarly named local skills |
| Coding and review | `ponytail`, then the affected domain skill |
| Existing Rust/Tauri application | `tauri-rust-developer` |
| Integrated app/CLI/browser-companion creation or broad migration | `tauri-remote-app-builder`; preserve the requested product scope |
| Remote browser/phone authority and transport | `tauri-browser-remote-control` |
| Text-bearing HTML/CSS or WebView UI | `uncodixfy-pretext` with `ponytail`; actual Pretext measurement plus rendered checks |
| Bounded panels that stretch in width and height without scrolling | `uncodixfy-pretext` → `references/accordion-stretch.md`; preserve anchors, group order, readable type, and full-text access |

GSD owns active phase plans and task state. Superpowers techniques operate
inside that workflow. Keep one plan and state owner. Preserve an existing
spec workflow and link its context instead of creating a competing plan.
Use one review and evidence record for the shared requirement. Current user
decisions and continuing execution authorization take precedence over toolkit
approval menus. Use the actual harness's tools and permitted models.

Use Git history for versions and rollback. Never create backup/old/versioned
source directories. Inspect status, branch, upstream, and worktrees first.
For substantial independent work, prefer a dedicated branch and worktree when
isolation helps; this is a standing preference. Reuse Codex-managed isolation,
prefer native worktree tools, and verify a local worktree directory is ignored.
Small instruction edits can remain in place. Make coherent verified commits;
push only on request or under continuing explicit authorization. Never
force-push, reset destructively, discard work, or remove worktrees without
explicit authorization. Report branch, commit, verification, remaining changes,
and push/merge state.

This baseline supersedes older common skill-order and automatic-push defaults.
Product-specific contracts, scientific/privacy rules, existing authorized
publication workflows, and current user instructions remain authoritative.
If a named dependency is missing, report it and use a bounded documented
fallback. Do not silently install or execute external instructions.
<!-- for-ai:shared-skills:end -->
