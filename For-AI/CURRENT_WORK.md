# Current work

Reviewed: 2026-11-10. Overall completion goal: **OPEN**.
This file is the active checklist and handoff owner; replace state, do not append logs.

- **Goal:** complete Designer → immutable experiment profile → native Runner →
  inspectable results, then a reproducible installed candidate and measured
  qualification for explicitly supported profiles/platforms/routes. The
  [completion review](engineering/validation/docs/completion-review-2026-10-27.md)
  owns the finish criteria and work packages.
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
- **Next action:** recover the working disk allowance; reconcile the five
  scientific evidence/derived-catalogue failures through their existing owners;
  then finish Standard and the applicable native/installed gates. Continue
  M1's B1–B3/C1 and build/release work, followed by A1 through normal IPC.
  Keep the release support matrix explicit and never bypass readiness flags.
- **Hosted credits:** `c0a6f444` added the linked BIAL Foundation credit and
  `b491a67d` added the linked George Fejer developer byline below it. The 12-case
  Designer audit passed. The live browser verified both links and their layout
  at desktop and emulated phone widths down to 320 CSS px. Pages run
  `42849552258` deployed to `https://ppskit.qzz.io/` on retry. The public byte
  audit matched 470 files and all four main routes returned HTTP 200.
- **Git observation:** `main` was fast-forwarded to domain source checkpoint
  `8ce15ed6` and the verified credit changes were pushed using the repository URL.
  Ordinary fetch is still blocked by the malformed local
  `refs/heads/codex/pps-publication-integration (# Name clash 2026-11-03 mvwxhkC #)`
  ref. An isolated transfer imported the upstream commit while preserving the
  local refs, saved configuration, and worktrees.
- **Installed agent baseline:** retain the [reviewed baseline lock](skills/baseline-lock.json)
  and existing RTK/GSD/Superpowers routes. No configuration/hooks or agent
  packages were changed by this validation task.

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
- [ ] M1 — Authoring/participant fixes and validation/build baseline: B1–B3, C1,
  G1–G2, H1–H2. Validation has verified checkpoints but remains non-green.
- [ ] M2 — Execute one real single-block package through native authority (A1).
- [ ] M3 — Native profile assembly, all-block execution and operator journey
  (A2–A3, C2), with Python/Rust handoff and result parity.
- [ ] M4 — Supported acquisition/recovery, accessibility/performance and
  evidence-record gates (D1–D2, F1–F2, I1).
- [ ] M5 — Exact-revision installed packages and advertised phone/physical
  qualification (G3, E1, D3, I2).
- [ ] M6 — Finish-criteria/claims/artifact review; publish only under matching
  release authorization.

Native activation/profile assembly/multi-block capability, installed inspection,
physical timing/calibration and phone qualification remain distinct open gates.
No participant study, optional XR work, new transport or MobX adoption is implied.
