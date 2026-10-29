# GitHub Pages Dashboard

The compiled Designer can be published as a static GitHub Pages interface while
the experiment software runs locally on the research PC. Local packaging and
Pages use the exact same `apps/designer/frontend/compiled/` bytes.

## Architecture

- GitHub Pages serves the visible dashboard UI.
- The hosted shell has three top tabs: `PPS Toolkit` for the Segment 0-6
  experiment workflow, `Documentation` for local/reference guides, and
  `Downloads` for installer/package links.
- The separate `/experiment-runner/` subpage serves the canonical Runner
  companion UI for controller and exploratory Phone Experiment modes. The
  Downloads page links to it.
- The hosted Designer uses browser-local drafts and audio in IndexedDB. It can
  inspect presets, configure premade assets, preview saved timing, save/reload,
  import fixed audio and export a portable `.pps-profile` bundle, including
  instruction audio. Selected files and drafts are not uploaded to Pages.
- Hosted preparation cannot generate new spatial audio or execute participant
  experiments. Changing a generation parameter invalidates the old preview;
  use the native Designer for Rust/3DTI generation and experiment preparation.
- Startup selects the hosted, Tauri or V1 local adapter explicitly. The hosted
  page does not connect to localhost. The V1 companion route is restricted to
  a loopback `/dashboard/` origin; a native error does not switch to hosted mode.
- The [Python-free Windows preview](NATIVE_WINDOWS_PREVIEW.md) describes native
  import, generation, ordered execution and result receipts. Its LSL, XDF and
  physical-capture limitations are explicit. The existing V1 Focus Mode has a
  separate Python/PySide workflow and acquisition outputs; those features are
  not implied by opening the hosted Designer or installing the native preview.
- Designer browser JavaScript does not own experiment timing. Timing-sensitive
  participant runs stay native-backed. The separate Runner companion can own an
  explicitly exploratory, locally armed phone demo using Web Audio and browser
  vibration, but it is not publication-grade timing evidence.
- The Documentation page includes a read-only, lazy-loaded PPS publication and
  citation network. It is a static GitHub Pages asset and never calls the local
  companion or moves literature metadata, PDFs, or participant data between the
  browser and the research PC.

## Audiotactile PPS Citation Map

The `Publication & Citation Network` documentation segment renders the tracked
`pps-publication-citation-network.v3` asset. It starts from 97 non-review
audio-tactile candidates but displays only the 94 publications for which the
normalized DOI, DOI-keyed identity, and canonical `https://doi.org/` link agree,
the dated exact-DOI resolver audit confirms the link, and an identified metadata
provider supplies a finite citation count. A valid zero
count is available citation metadata; a missing provider record is not. The
displayed set contains 90 publications retained from the original manual
confirmation audit and 4 added by later exact-DOI Toolkit literature audits.
Its 750 tracked directed citation links run from the citing publication to the
cited publication: 571 come from the frozen multi-source snapshot and 127 from
a non-overlapping, dated exact-DOI OpenAlex refresh. The retained graph also
includes 52 of 60 links verified directly in six primary reference lists; the
other 8 originate from the two DOI-less source records excluded by the stricter
node policy.

The visible introduction presents this set as a curated cross-section for
understanding the main audio–tactile PPS paradigms and design variations that
inform the Toolkit. It is an orientation to the field, not a systematic or
exhaustive review. The compact topology/year choice and map key sit below the
graph, while live status, node-size guidance, and Full screen remain above it.

The default topology is a real deterministic force layout, not a ranked grid:
citation neighbours attract, all papers repel and share weak centering, and
radius-aware collision separation keeps every node distinct on the same square
plotting surface at desktop and phone widths. The 91-node main
component uses the map broadly, while 3 records with no verified within-map link
settle under the same force rule instead of occupying an artificial perimeter.
Circle area encodes normalized citations received within the displayed network.
Specifically, each radius is derived only from the number of incoming links from
the other 93 displayed papers, using a monotonic log-normalized area scale from
`0.009` to `0.024`; external citation totals and centrality do not size nodes.
The declared normalized edge-to-edge clearance is `0.015` in both layouts.
All 750 eligible-set links remain visible; selecting a paper emphasizes and distinguishes
incoming from outgoing citations. The optional year layout
anchors horizontal position to publication year while retaining collision separation.

Search and stable selection links open publication and experiment-level details,
including the eleven compact replication contracts, source/page pointers,
derivation formulas and explanations of missing or conflicting evidence. The
mapper displays parameter review, template availability and tested native
capability separately. Counts and status summaries come from the generated
network and study-review projection rather than a manually maintained total.
Assessed source gaps remain visible; reviewed coverage does not make an
incomplete preset replication-ready or establish native/physical qualification.
Details also retain bibliographic metadata, abstract provenance and directional
citation neighbours.
When a paper record declares bundled Toolkit template IDs, its details show one
new-tab Designer link for every deduplicated ID, including profiles that remain
parameter-incomplete. The link targets the shared dashboard with
`page=toolkit&template=<template_id>#study-segment`. The Designer validates the
ID against its built-in template catalogue and loads it once through the selected
adapter; papers without a
declared template show no template-link section.

The canonical v1 source remains the broader dated snapshot of 1,712 publications
and 10,109 citation edges. It is retained for reproducible provenance and future
audit work but is not the browser view. Neither the source nor the focused
projection is a systematic review, exhaustive bibliography, study-quality
ranking, or effect-size analysis. The inclusion audits, citation graph, and
metadata providers have dated and incomplete coverage.
Abstract text is included only where the generator records redistributable
OpenAlex provenance; otherwise the asset exposes a copyright caveat and source
link. Raw provider payloads, PDFs, supplements, extracted full text, and fuzzy
parameter matches do not belong in the public dashboard asset.

The canonical public-safe source snapshot lives in `For-AI/research/literature/publication-network/`.
Rebuild the network, then its sanitized study-review projection after changing
that snapshot, source reviews, study inventories or DOI-linked parameter audits:

```bash
node For-AI/research/literature/tools/build_publication_network_asset.mjs
node For-AI/research/literature/tools/build_publication_parameter_review_matrix.mjs
```

For a deliberate initial refresh from a locally held network bundle, pass the
bundle explicitly; the bundle itself is not committed:

```bash
node For-AI/research/literature/tools/build_publication_network_asset.mjs --source-bundle /path/to/pps-citation-network-YYYYMMDD
```

Then run the publication-network tests and rebuild Vite so the packaged/local
and GitHub Pages dashboards receive the same source and generated data:

```bash
python -m pytest For-AI/engineering/tests/test_publication_network.py
npm --prefix apps/designer/frontend run build
```

The default data rebuild must be deterministic. Review the generated JSON diff,
run the dashboard visual-layout audit, inspect its desktop/mobile light/dark
screenshots, and publish the source dashboard, compiled dashboard, public
wrappers, data snapshot, tests, and project-memory changes together.

## Publish

GitHub Pages deploys the artifact assembled by
`For-AI/engineering/automation/build_pages.mjs` through the thin
`.github/workflows/pages.yml` wrapper. The assembly copies `website/` route
inputs, the compiled Designer, the allowlisted compiled Runner companion files,
approved catalogues, and `website/CNAME` into ignored `dist/pages/`. The public
dashboard URL is:

```text
https://ppskit.qzz.io/
```

The GitHub Pages fallback URL is:

```text
https://georgefejer91.github.io/pps-kit/
```

The Runner companion URLs are:

```text
https://ppskit.qzz.io/experiment-runner/
https://georgefejer91.github.io/pps-kit/experiment-runner/
```

The page files are byte-identical to the local compiled companion and contain
no Tauri bridge. GitHub Pages does not provide WebSocket upgrades. Phone
Experiment mode can run locally in the hosted page. The existing authenticated
VDO/WSS/WebRTC companion route requires explicit activation and pairing; it
still needs qualification for the advertised phone and network. Its presence
does not establish publication-grade acquisition timing.

The `github.com/GeorgeFejer91/pps-kit` URL is the GitHub repository/code view.
The assembled Pages root `index.html` loads the copied compiled Designer, and
the assembled root `CNAME` comes from `website/CNAME`. Relative static paths
allow the same compiled files to work on Pages and through local FastAPI.

## Use On A Research PC

Install the toolkit once:

```powershell
.\For-AI\engineering\build\windows\Setup_Windows_App.ps1
```

Start the local companion backend:

```bat
apps\designer\launchers\Start_Website_Companion.bat
```

Open the local `/dashboard/` URL printed by the launcher for the V1 companion
workflow. Opening GitHub Pages instead selects browser-local preparation. Use
the [native preview guide](NATIVE_WINDOWS_PREVIEW.md) for the separate Windows
Rust/Tauri route; the scripts above install the V1 compatibility environment.

## Safety Boundary

A public website cannot silently install Python, packages, audio drivers, or
experiment dependencies. The download route offers separate Designer, Runner,
and Full bootstrapper artifacts when their matching GitHub Release assets
exist. Heavy payloads may live on Zenodo. Installation happens locally, and
each downloader verifies its component-specific payload and inventory hashes
before extraction or launch.

The companion backend allows the default project GitHub Pages origin
(`https://georgefejer91.github.io`) and the custom domain
(`https://ppskit.qzz.io`). For forks or institutional Pages domains, start the
companion with an explicit origin:

```bat
apps\designer\launchers\Start_Website_Companion.bat --web-origin https://example.github.io
```

Use `--no-default-web-origin` if only a custom origin should be allowed.
