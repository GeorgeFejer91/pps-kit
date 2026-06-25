# Installer Content Orchestration

The installed payload is a repo-shaped program directory for researchers, not the full development workspace.

## Include

- `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe` and its onedir resources.
- `dist/PPSExperimentRunner/PPSExperimentRunner.exe` and its onedir resources.
- `dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll`.
- Dashboard/static assets: `src/peripersonal_space_toolkit/dashboard/`, `src/peripersonal_space_toolkit/viewer/`, root `index.html`, `.nojekyll`.
- Runtime assets: `assets/preloads/`, `assets/breathing/`, `assets/click/`, `assets/tactile/`, and the approved FABIAN SOFA asset.
- Researcher-facing source/config/docs: `src/`, `configs/`, `study_templates/`, `data/sample/`, `docs/`, `README.md`, `LICENSE`, `THIRD_PARTY_LICENSES.md`, `CITATION.cff`.
- Windows launchers and build/audit helpers needed to inspect the installation.
- `installer_protocols/` so installer package decisions and missing links are visible in the installed package.

## Exclude

- `For-AI/`; it is source-repo project memory for future agents, not an end-user install surface.
- `dist/` artifacts other than the staged packaged exes copied into the payload.
- Generated sessions, participant outputs, XDF/WAV validation artifacts, model caches, private paths, credentials, raw recordings, and local hardware notes.

## Entrypoints

The manifest dashboard shortcut targets `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe`. Batch launchers remain included for source-mode fallback and inspectability, but end users should not need Python to open the installed local dashboard or runner.
