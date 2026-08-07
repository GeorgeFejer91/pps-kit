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

The Documentation page projects the tracked
`pps-publication-citation-network.v1` snapshot into an audiotactile-first study
browser. Its default and only primary graph contains the 101 papers whose
audiotactile modality was manually verified. `Citation map` uses deterministic
coordinates fitted to the induced 101-paper network; `By year` fits the same
papers to their 2000-2026 publication range. The broader 1,712-paper PPS corpus
remains in the generated public asset but is not mixed into the default visual
surface.

The primary controls are search, the two-view switch, and reset. A persistent
study list is sorted by citations received from other verified audiotactile
papers. Circle size uses that same within-audiotactile count. On spacious maps,
several landmark papers are labelled directly; below 520 px, persistent labels
are removed until a paper is selected or hovered. Selecting a node or list row
centers it, replaces the list with a compact detail panel, and highlights
incoming and outgoing citations with separate line colors and arrowheads.
Abstracts, evidence notes,
toolkit parameter audits, and full-corpus PageRank/betweenness remain available
through progressive disclosure. Missing or unaudited fields are displayed
explicitly rather than inferred.

Verified modality labels and provisional keyword candidates remain separate in
the data. No non-verified paper may be presented as an audiotactile study, and
the 164 visuotactile lexical candidates remain explicitly provisional rather
than becoming part of this map.

The public snapshot is a broad, dated PPS discovery corpus, not a systematic
review, exhaustive bibliography, study-quality ranking, or effect-size
analysis. Centrality values describe this snapshot only. Citation direction is
`citing -> cited`. Abstract text is included only where the generator records a
redistributable OpenAlex source; otherwise the public asset carries an
availability/copyright caveat and links researchers to the publication source.
Raw provider payloads, PDFs, supplements, extracted full text, and fuzzy
parameter matches do not belong in the public dashboard asset.

The 2026-08-07 snapshot contains 1,712 publication nodes and 10,109 citation
edges. It has 101 manually verified audiotactile nodes, no manually verified
visuotactile nodes, and 164 explicitly provisional visuotactile lexical
candidates. Exact DOI matching attaches 73 toolkit literature-audit records to
69 publication nodes; repeated task records for one paper remain separate.
Forty-two abstracts are included with OpenAlex CC0 metadata provenance and an
underlying-publication copyright caveat; all other abstract states remain
link-only or unavailable.

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
