# Current work

Reviewed: 2026-11-12. Overall completion goal: **OPEN**.
This file is the active checklist and handoff owner; replace state, do not append logs.

- **Goal:** deliver the [standalone study preview PWA and offline Planner +
  Runner suite](evolving_goals.md#2026-11-10--two-ways-to-use-pps-kit), with the
  refreshed UI and three Windows editions (Planner, Runner, and their suite).
  The existing
  [completion review](engineering/validation/docs/completion-review-2026-10-27.md)
  owns native work packages and qualification gates.
- **Browser launch: VERIFIED.** Pages [run 43051771734](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43051771734)
  deployed source checkpoint 48b42e1 to [ppskit.com](https://ppskit.com/).
  All 474 staged files matched the public site and the four public routes
  returned HTTP 200. Chromium verified PWA installability, keyboard playback
  and an offline revisit for Study 5, plus Downloads reflow at 320 CSS px.
  The Experiment Runner tab opens a top-level browser Runner. Two independent
  Chromium contexts paired over live VDO.Ninja on both local Pages staging
  and public HTTPS. The controller could start only after local arming; the
  test observed the vibration API call through an instrumented adapter.
  Physical vibration, device timing and native acquisition are separate
  qualification gates. The Windows release remains a draft with no installer
  assets; Downloads lists the three editions without inventing asset URLs.
- **Installer and app icons: VERIFIED LIVE.** Downloads shows a distinct SVG
  for Planner, Runner and Suite. Planner retains its radar artwork. Runner's
  play icon is used by its browser tab, Qt windows and native build settings.
  The three local Windows downloaders matched all seven embedded sizes, and
  Windows loaded each icon. The rebuilt legacy Runner executable also matched
  all seven embedded sizes and passed its Qt runtime and startup checks.
  Chromium verified the public cards at 1440 CSS px
  in light mode and 390 CSS px in dark mode. The local 320 CSS px check
  included 200% text and spacing. All 477 staged files matched the public
  site and the four main routes returned HTTP 200. Pages
  [run 43211295270](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43211295270)
  deployed `6e74400`. Both local Vite previews also served the SVGs.
  The public Windows release remains a draft.
- **Designer header: VERIFIED LIVE.** Runner and the light/dark switch share
  the 53 CSS px pinned phone row. The phone Planner omits the browser preview
  badge. Save status, Help and credits scroll with the page. The section
  disclosure opens a four-column grid on narrow phones
  and a single seven-column row from 600 to 760 CSS px. Pretext selects readable
  label sizes and preserves enlarged text with wrapping. The wide heading still
  docks below the page tabs. The 12-case local audit and live Chromium checks
  covered 320–760 CSS px, resizing, light and dark themes, touch, keyboard focus,
  and 200% text with spacing. Pages [run 43206039793](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43206039793)
  deployed `9e4b36a` to [ppskit.com](https://ppskit.com/). A legacy offline cache
  reproduced the old phone header. Online navigation now fetches current HTML,
  while the offline preview retains a complete snapshot. The older browser
  picked up the fix on reload and kept its existing tab and previous assets.
  Live Chromium verified the current header and cached Study 5 playback.
  Pages [run 43208031434](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43208031434)
  deployed `6c3c324`. All 474 staged files and four public routes passed.
  Pages [run 43211778280](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43211778280)
  deployed `40fb1ef`. Live Chromium verified the 320 CSS px Planner row, theme
  touch and keyboard interaction, the direct Planner link, and the on-device
  Runner demo with an instrumented vibration call. All 477 staged files matched
  the site and all four public routes returned HTTP 200.
- **Browser Runner layout: VERIFIED LIVE.** Planner, Runner, Documentation
  and Downloads share the header, sidebar geometry and theme placement. The
  Runner's modes sit in the sidebar. Its public route opens directly for
  pairing and local output controls. Pages
  [run 43248773920](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43248773920)
  deployed `52c5dd2` to [ppskit.com](https://ppskit.com/). Live Chromium
  verified that the tabs and sidebar keep their positions through navigation
  at 320, 1440 and 1920 CSS px. The browser demo also passed. Local Chromium
  checked both themes at 320–2560 CSS px, including landscape, keyboard,
  touch, resizing and 200% text with spacing. Both canonical builds, 65
  Runner tests, 18 layout contract tests, the 12-case Designer audit, offline
  Study 5 and both Pages assembly checks passed. All 477 public files matched
  staging and all four routes returned HTTP 200. The checkpoint was pushed
  from a clean checkout because the primary checkout reported staged deletions
  and a Git mmap error.
- **Current stage:** verified Designer source. The public Designer opens
  directly as a browser preview with bundled study assets. The connection
  panel and localhost probe were removed in `d45c0c8`. Live Chromium checked
  Study 5 playback and Downloads at desktop and phone widths after
  [Pages run 43049923380](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43049923380).
  The local source launcher passed its cookie-authenticated profile change.
  The Windows installer release is still a draft. The
  [HTML layout standard](interface_design_principles.md#default-html-layout-uncodixfy-pretext-stretch-accordion)
  is now the stretch accordion. The ingredient configuration row has a
  mouse/keyboard divider and a square, centered 2D preview. Chromium checks
  covered Study 5 in View mode, both drag directions, keyboard focus/resize,
  2D/3D controls, light/dark, and 320 CSS px reflow with text spacing.
  The canonical rebuild and both Pages assembly tests passed from a clean
  snapshot after the primary checkout's cloud file provider blocked a preload
  read. GitHub Pages [run 43048600160](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43048600160)
  deployed source checkpoint `0b76e118` to `https://ppskit.com/`. Live Chromium
  confirmed the same interaction and layout; all 470 public files matched
  staging and the four main routes returned HTTP 200. The offline suite and
  installed validation remain open.
- **Trajectory preview: VERIFIED LIVE.** The square, square-cornered frame
  contains the full canvas at fractional and high device pixel ratios. Its
  opening 2D view centers and fits the circle, including when a study changes
  the radius. Local and live Chromium checked 320–1920 CSS px, reloads, a
  cached offline revisit, a study switch, 2D/3D, Fit Radius and Reset Camera.
  The 12-case Designer audit and both Pages assembly tests passed.
  At 320 CSS px with 200% text and spacing, the preview fits and the existing
  stimulus status row below it still overflows by 14 CSS px. Pages
  [run 43246515501](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43246515501)
  deployed `1c36f6b`. All 477 staged files matched the public site and the
  four main routes returned HTTP 200. The source checkpoint was pushed from
  a clean worktree because the primary checkout reported a Git mmap error.
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
- **Next product slice:** expand PWA coverage only to cleared, verified assets.
  Exercise browser audio and vibration on a physical supported phone before
  qualifying that device route. In the native track,
  recover the working disk allowance; reconcile the five
  scientific evidence/derived-catalogue failures through their existing owners;
  then finish Standard and the applicable native/installed gates. Continue
  M1's B1–B3/C1 and build/release work, followed by A1 through normal IPC.
  Keep the release support matrix explicit and never bypass readiness flags.
- **Hosted credits:** `5b269569` moved the George Fejer credit into the hosted
  Designer header as a linked profile box with the portrait from his academic
  site. The BIAL Foundation credit remains beside it. The 12-case Designer
  audit and narrow-phone rechecks passed; live desktop and 320 CSS px phone
  checks verified the portrait, keyboard focus, and link activation. Pages run
  `42867609777` deployed to `https://ppskit.com/`; 470 public files matched
  the assembled bytes and all four main routes returned HTTP 200. No installer
  was rebuilt.
- **Designer noise picker:** White, Pink, Blue, Violet and Brown retain their
  named fills in Edit and use muted tints in View. Chromium checks passed in
  both themes at 320 to 1920 CSS px, including selection, focus, label contrast
  and text spacing. The canonical build and Pages assembly passed. Installed
  validation remains a separate gate.
- Runnable citation-map papers now open their linked study in Experiment
  Designer in the same tab. Source commit `342560e` reached GitHub `main`.
  Chrome verified Serino, Biggio, and Noel trajectory loads, keyboard launch,
  320 CSS px reflow, 200% label sizing, and saved-draft preservation on the
  live site. All 28 Designer files matched the local build and four public
  routes returned HTTP 200. Eight network tests and two Pages assembly tests
  passed. The catalogue status and determinism failures reproduced on the
  baseline. Installed verification remains open.
  [Pages deployment](https://github.com/GeorgeFejer91/pps-kit/actions/runs/43050622016).
- **Git observation:** the standalone browser source checkpoint was pushed
  to `main` and `codex/pps-browser-standalone` from a clean secondary checkout.
  The primary checkout's cloud-provider read error blocked Git worktree creation.
- **Goals checkpoint:** For-AI documentation only, based on `5b269569`
  already on GitHub `main`.
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
- [x] PWA — Verify installability and a cached revisit for the supported Study 5 preview.
- [x] Browser Runner — Publish the Runner tab and verify the built-in demo and
  consent-based beacon pairing over the public HTTPS route.
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
