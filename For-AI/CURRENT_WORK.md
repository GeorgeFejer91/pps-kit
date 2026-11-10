# Current work

Reviewed: 2026-11-10. Overall completion goal: **OPEN**.
This file is the active checklist and handoff owner; replace state, do not append logs.

- **Goal:** deliver the [standalone study preview PWA and offline Planner +
  Runner suite](evolving_goals.md#2026-11-10--two-ways-to-use-pps-kit), with the
  refreshed UI and one suite installer. The existing
  [completion review](engineering/validation/docs/completion-review-2026-10-27.md)
  owns native work packages and qualification gates.
- **Current stage:** local browser preview on
  `codex/pps-standalone-preview` from public base `8b684954`. The
  [browser audit](engineering/validation/scripts/run_study_preview_audit.py)
  verified Study 5 and Canzoneri selection/playback, a saved-backend isolation
  check, keyboard focus, Chromium installability, offline Study 5 replay, and
  320 CSS px layout with enlarged text. The built cache contains 60 files
  (5.4 MB), including two verified Study 5 WAVs. Chrome's headless install
  command timed out. An installed PWA launch and source promotion remain open.
- **Desktop baseline:** three profile, Runner software and marker loopback
  tests passed. Native 3DTI rendered a 3 s brown-noise trajectory with two
  audio channels and a tactile channel at 44.1 kHz. An absolute output path
  worked. The relative CLI output path failed because the renderer runs
  from the resource root.
- **Suite source:** frozen Planner and Runner now resolve the installer-owned
  Shared directory and workspace. Planner resolves Runner and native 3DTI in
  the suite. Removed duplicate scientific assets from the frozen app specs.
  Twenty-five focused Python checks, the Qt preflight and the downloader
  tests passed. Rebuild the Windows Full package and verify the generated
  stimulus → profile → Runner handoff through installed entrypoints.
- **Current milestone:** M1, partial. The requested validation task delivered
  verified source fixes and a retained validation run; full validation sign-off
  remains open. M0 setup/review is complete.
- **Source checkpoints:** `ba088bb9` pins shared browser modules to LF;
  `3baff2dd` rejects accepted-block regeneration before queueing while retaining
  the worker race guard; `e2676481` fixes SVG newline, minified CSS, routed
  guidance and Windows long-path validation; `0208ca0d` pins Vite 6.4.5 and
  source-map-js 1.2.2 in both frontend locks. All four were committed/pushed.
  Rebuilt canonical frontend bytes remain identical to the prior committed
  artifacts. No installed application or public download was rebuilt here.
- **Verified locally:** Quick (30 tests), Rust 1.88 Core fmt/check/Clippy and
  127 tests/doctests; three Python/Rust differential tests; 55 session/diary/
  response checks; two block regressions and eight generation/job checks;
  two prepared-profile/loopback software smokes; the Windows profile-local
  package regression; 21 frontend contract checks; Runner's 65 frontend tests;
  both clean npm installs/builds and zero-advisory audits; Go 1.22.12 downloader
  tests; two Pages assembly checks. These are software evidence.
- **Rendered/public evidence:** inspected Designer audit (12 cases), participant
  and output audits (six each), and shared text/lifecycle audit (15). Runner
  audits use a mocked native bridge. Public byte audit passed 470 files and
  four main routes after the dependency-patch deployment. Latest CI/deployment
  observations are retained in the implementation record and checked at handoff.
- **Standard gate: BLOCKED / NON-GREEN.** The first complete run collected 639
  tests: 573 passed, 19 failed, 37 setup errors, 10 skipped. Fourteen failures
  and all 37 setup errors subsequently passed owning rechecks. Five independent
  publication/evidence checks still fail: a review's schema/provenance metadata,
  catalogue status/determinism, and orientation-review counts. Their assertions
  and scientific records were preserved. A fresh guarded Standard retry stopped
  below 192 MiB free; it did not finish. Do not aggregate focused passes into a
  claimed Standard pass. See the [implementation record](engineering/validation/docs/implementation-status-2026-09-27.md).
- **Storage:** the former shortage has returned. The volume began near 2.2 GiB
  free, reached zero during the first combined run, and recovered to under
  1 GiB after generated-cache compression and test cleanup. Allow approximately
  15 GiB before another complete Python/native run. No unrelated files,
  worktrees or failed-run records were removed. Detailed logs, screenshots,
  schema findings and the temporary Go toolchain stay in ignored artifacts.
- **Next gates:** verify an installed PWA launch and the public bytes at
  source promotion. In the native track, recover the working disk allowance
  (about 8.2 GiB free at this checkpoint), reconcile the five evidence/catalogue
  failures through their owners, and complete Standard. Continue M1 and A1
  through normal IPC with the applicable native and installed gates.
- **Hosted credits:** `5b269569` moved the George Fejer credit into the hosted
  Designer header as a linked profile box with the portrait from his academic
  site. The BIAL Foundation credit remains beside it. The 12-case Designer
  audit and narrow-phone rechecks passed; live desktop and 320 CSS px phone
  checks verified the portrait, keyboard focus, and link activation. Pages run
  `42867609777` deployed to `https://ppskit.com/`; 470 public files matched
  the assembled bytes and all four main routes returned HTTP 200. No installer
  was rebuilt.
- **Git observation:** `main` was fast-forwarded to domain source checkpoint
  `8ce15ed6` and the verified credit changes were pushed using the repository URL.
  Ordinary fetch is still blocked by the malformed local
  `refs/heads/codex/pps-publication-integration (# Name clash 2026-11-03 mvwxhkC #)`
  ref. An isolated transfer imported the upstream commit while preserving the
  local refs, saved configuration, and worktrees.
- **Goals checkpoint:** For-AI documentation only, based on `5b269569`
  already on GitHub `main`. Fetch still hits the malformed ref above.
  Guidance links/anchors, diff whitespace, and five repository/release audit
  tests passed. These documentation paths do not trigger the Pages workflow.
- **Installed agent baseline:** retain the [reviewed baseline lock](skills/baseline-lock.json)
  and existing RTK/GSD/Superpowers routes. No configuration/hooks or agent
  packages were changed by this validation task.
- **Publication archive:** original PDFs and working extraction protocols
  have a separate private home. The current Pages assembly tests pass, and the
  component manifests exclude `For-AI/` and local research artifacts. Continue
  paper acquisition from the archive's DOI inventory. No release was rebuilt.

## Domain migration — 2026-11-10

**Primary URL: VERIFIED.** `https://ppskit.com/` is the live canonical site
and the GitHub repository's Website link. Public routes and native experiment
boundaries are unchanged. Keep `ppskit.qzz.io` as a legacy CORS origin only.

- [x] Identify the live-source repository, Actions Pages workflow, tracked
  `CNAME`, strict Pages assembly expectation, and companion allowlist.
- [x] Align `website/CNAME`, Pages assembly/tests, public links and
  documentation with `ppskit.com`; allow the new apex/`www` origins locally.
- [x] Save `ppskit.com` in GitHub repository Settings → Pages as the Actions
  custom domain; verify GitHub reports the configured domain.
- [x] In Namecheap remove the apex redirect to `www` and the parked
  `www` CNAME; add the four GitHub Pages apex A records and
  `www → georgefejer91.github.io` CNAME. Preserve unrelated mail/TXT.
- [x] Confirm deployed main commit, successful Pages Action, public DNS
  resolution, GitHub Pages domain check, HTTPS certificate/enforcement and
  `www` → apex redirect.
- [x] Open `https://ppskit.com/`, `/documentation/`, `/download/` and
  `/experiment-runner/`, checking rendered content and static assets. Test
  local companion CORS from the new origin.
- [x] Set the GitHub repository Website link and the Designer Downloads
  Runner Companion link to the new domain. Follow the live Runner link and
  GitHub Pages fallback in a fresh browser.

**Evidence/status:** GitHub Actions run `42852101001` deployed `2099e2fd` to
`https://ppskit.com/`. Both domains passed GitHub's DNS check; HTTPS is enforced
and the certificate covers the apex and `www`. A fresh Chrome session loaded
all four routes, followed the live Runner link and reached the apex from the
GitHub Pages fallback. The byte audit matched 470 files. The local companion
accepted apex/`www` origins and the apex preflight. A GitHub edge cache still
returned the previous redirect for a fallback request without compression;
recheck that cache variant if the old redirect is reported again. See
`docs/GITHUB_PAGES_DASHBOARD.md`.

## Active completion checklist

- [x] M0 — Install the baseline, integrate routes and produce the completion review/plan.
- [x] Record the two product goals, acceptance criteria, and lean For-AI protocols.
- [x] PWA local preview — Study 5 and Canzoneri playback, browser UI, and cached
  Study 5 revisit verified against the assembled site.
- [ ] PWA promotion — Verify standalone launch after installation, then verify
  the public routes and byte parity on the promoted revision.
- [ ] M1 — Authoring/participant fixes and validation/build baseline: B1–B3, C1,
  G1–G2, H1–H2. Validation has verified checkpoints but remains non-green.
- [ ] M2 — Execute one real single-block package through native authority (A1).
- [ ] M3 — Native profile assembly, all-block execution and operator journey
  (A2–A3, C2), with Python/Rust handoff and result parity.
- [ ] M4 — Supported acquisition/recovery, accessibility/performance and
  evidence-record gates (D1–D2, F1–F2, I1).
- [ ] M5 — Build one exact-revision installer for Planner and Runner with one
  Shared payload. Verify offline generation, profile handoff and a supported
  run on a clean installation; qualify advertised phone/physical routes
  separately (G3, E1 when advertised, D3, I2).
- [ ] M6 — Finish-criteria/claims/artifact review; publish only under matching
  release authorization.

Native activation/profile assembly/multi-block capability, installed inspection,
physical timing/calibration and phone qualification remain distinct open gates.
No participant study, optional XR work, new transport or MobX adoption is implied.
