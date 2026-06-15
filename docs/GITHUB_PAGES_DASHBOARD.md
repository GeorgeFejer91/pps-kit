# GitHub Pages Dashboard

The HTML dashboard can be published as a static GitHub Pages interface while the
experiment software runs locally on the research PC.

## Architecture

- GitHub Pages serves the visible dashboard UI.
- The local companion backend runs on the PC at `http://127.0.0.1:8766`.
- The hosted page calls the companion API for design state, render jobs, session
  preparation, audio stress tests, and native Focus Mode launch.
- Segment 6 passes the prepared run setup to the local backend. Native Focus
  Mode owns participant metadata and runtime options; live LSL/event markers,
  local marker mirrors, trigger dictionaries, `events.csv`, and analysis CSVs
  are standard runner outputs, while the full-audio evidence WAV remains an
  optional runner checkbox.
- File imports are local companion actions. Selected stimulus audio is copied
  into ignored local data on the research PC; it is not uploaded to GitHub
  Pages or any online service.
- Browser JavaScript does not own experiment timing. Timing-sensitive participant
  runs stay native/Python-backed.

## Publish

Enable GitHub Pages for the repository branch root. The public dashboard URL is:

```text
https://georgefejer91.github.io/peripersonal-space-toolkit/
```

The `github.com/GeorgeFejer91/peripersonal-space-toolkit` URL remains the GitHub
repository/code view. The Pages root `index.html` displays the dashboard from the
same packaged dashboard assets instead of redirecting visitors to a nested source
path. The dashboard uses relative static paths, so the same files work when
served from GitHub Pages or from the local FastAPI app.

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
(`https://georgefejer91.github.io`). For forks or institutional Pages domains,
start the companion with an explicit origin:

```bat
windows\Start_Website_Companion.bat --web-origin https://example.github.io
```

Use `--no-default-web-origin` if only a custom origin should be allowed.
