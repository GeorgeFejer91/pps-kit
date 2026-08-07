# GitHub Pages Dashboard

The HTML dashboard can be published as a static GitHub Pages interface while the
experiment software runs locally on the research PC.

## Architecture

- GitHub Pages serves the visible dashboard UI.
- The hosted shell has three top tabs: `PPS Toolkit` for the Segment 0-6
  experiment workflow, `Documentation` for local/reference guides, and
  `Downloads` for installer/package links.
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
- Browser JavaScript does not own experiment timing. Timing-sensitive participant
  runs stay native/Python-backed.
- The Documentation page includes a read-only, lazy-loaded PPS publication and
  citation network. It is a static GitHub Pages asset and never calls the local
  companion or moves literature metadata, PDFs, or participant data between the
  browser and the research PC.

## Audiotactile PPS Citation Map

The `Publication & Citation Network` documentation segment renders the tracked
`pps-publication-citation-network.v3` asset. It contains 97 non-review
audio-tactile publications: 93 retained from the original manual confirmation
audit and 4 added by later exact-DOI Toolkit literature audits. Its 571 directed
citation links run from the citing publication to the cited publication.

The default topology is a real deterministic force layout, not a ranked grid:
citation neighbours attract, radius-aware collision separation keeps every node
distinct, and 22 isolates occupy a stable square perimeter. Circle area encodes
normalized citations received within the displayed network. All links remain
faint for context; selecting a paper emphasizes and distinguishes incoming from
outgoing citations. The optional year layout anchors horizontal position to
publication year while retaining collision separation.

The legend exposes four Toolkit assessment states: 15 runnable, 49 supported
but parameter-incomplete, 32 not yet assessed, and 1 adjacent/scope-conflict
publication. Selecting a node opens bibliographic metadata, abstract
availability/provenance, directional citation neighbours, and every exact-DOI
Toolkit audit record and extracted parameter available for that publication.

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

The canonical public-safe source snapshot lives in `data/publication_network/`.
Rebuild the generated dashboard asset after changing that snapshot, modality
reviews, or DOI-linked parameter audits:

```bash
node tools/build_publication_network_asset.mjs
```

For a deliberate initial refresh from a locally held network bundle, pass the
bundle explicitly; the bundle itself is not committed:

```bash
node tools/build_publication_network_asset.mjs --source-bundle /path/to/pps-citation-network-YYYYMMDD
```

Then run the publication-network tests and rebuild Vite so the packaged/local
and GitHub Pages dashboards receive the same source and generated data:

```bash
python -m pytest tests/test_publication_network.py
npm --prefix src/peripersonal_space_toolkit/dashboard run build
```

The default data rebuild must be deterministic. Review the generated JSON diff,
run the dashboard visual-layout audit, inspect its desktop/mobile light/dark
screenshots, and publish the source dashboard, compiled dashboard, public
wrappers, data snapshot, tests, and project-memory changes together.

## Publish

Enable GitHub Pages for the repository branch root. The public dashboard URL is:

```text
https://ppskit.qzz.io/
```

The GitHub Pages fallback URL is:

```text
https://georgefejer91.github.io/pps-kit/
```

The `github.com/GeorgeFejer91/pps-kit` URL is the GitHub repository/code view.
The Pages root `index.html` displays the dashboard from the same packaged
dashboard assets instead of redirecting visitors to a nested source path. The
dashboard uses relative static paths, so the same files work when served from
GitHub Pages or from the local FastAPI app.

## Use On A Research PC

Install the toolkit once:

```powershell
.\windows\Setup_Windows_App.ps1
```

Start the local companion backend:

```bat
windows\Start_Website_Companion.bat
```

Then open the GitHub Pages dashboard. The left rail shows the local companion
status and lets the user set the backend URL if a non-default port is used.

## Safety Boundary

A public website cannot silently install Python, packages, audio drivers, or
experiment dependencies. The dashboard includes a `Download Installer` link for
the small GitHub-hosted PPS downloader plus a secondary full-package link for
the Zenodo-hosted offline lab ZIP. Installation still happens locally on the
research PC, and the downloader verifies `pps_download_manifest.v1.json` hashes
before extracting or launching software.

The companion backend allows the default project GitHub Pages origin
(`https://georgefejer91.github.io`) and the custom domain
(`https://ppskit.qzz.io`). For forks or institutional Pages domains, start the
companion with an explicit origin:

```bat
windows\Start_Website_Companion.bat --web-origin https://example.github.io
```

Use `--no-default-web-origin` if only a custom origin should be allowed.
