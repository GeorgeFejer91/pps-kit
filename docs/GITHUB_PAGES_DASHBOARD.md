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
- The local companion backend runs on the PC at `http://127.0.0.1:8766`.
- The hosted page calls the companion API for design state, render jobs, session
  preparation, audio stress tests, and native Focus Mode launch.
- If the local companion is not running, the hosted dashboard falls back to a
  static read-only profile mode backed by committed GitHub assets. It loads the
  preload inventory from `assets/preloads/preload_inventory.json`, loads study
  profile design JSON from `study_templates/`, and opens on the Study 5
  `study5_box_breathing_pps` profile by default. In this mode researchers can
  inspect existing profile parameters, source inventories, trajectory previews,
  and browser-play committed WAV assets. Creating new custom studies, importing
  files, baking new looming stimuli, materializing trial/block/session files, or
  opening Focus Mode still requires the local companion.
- Segment 6 passes the prepared run setup to the local backend. Native Focus
  Mode owns participant metadata and runtime options; live LSL/event markers,
  local marker mirrors, trigger dictionaries, `events.csv`, and analysis CSVs
  are standard runner outputs, while the fail-safe local recording WAV remains
  an optional runner checkbox.
- File imports are local companion actions. Selected stimulus audio is copied
  into ignored local data on the research PC; it is not uploaded to GitHub
  Pages or any online service.
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

The map legend exposes two implementation states: 15 implemented and 79 not
implemented yet. Selecting a node still exposes the full four-state assessment
(15 runnable, 49 supported but parameter-incomplete, 29 not yet assessed, and
1 adjacent/scope conflict) alongside bibliographic metadata, abstract
availability/provenance, directional citation neighbours, and every exact-DOI
Toolkit audit record and extracted parameter available for that publication.
When a paper record declares bundled Toolkit template IDs, its details show one
new-tab Designer link for every deduplicated ID, including profiles that remain
parameter-incomplete. The link targets the shared dashboard with
`page=toolkit&template=<template_id>#study-segment`. The Designer validates the
ID against its built-in template catalogue and loads it once through committed
static assets or the existing local companion endpoint; papers without a
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
Rebuild the generated dashboard asset after changing that snapshot, modality
reviews, or DOI-linked parameter audits:

```bash
node For-AI/research/literature/tools/build_publication_network_asset.mjs
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
Experiment mode can run locally in the hosted page, but cross-device BRSP
pairing requires a browser-side WSS/WebRTC adapter and endpoint to be
implemented/configured, deployed, and qualified together.

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

Then open the GitHub Pages dashboard. The left rail shows the local companion
status and lets the user set the backend URL if a non-default port is used.

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
