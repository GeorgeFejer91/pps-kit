# For-AI Project Memory

This folder is the required starting point for AI agents working on the Peripersonal Space Toolkit.

Read this file before modifying the repository. Then read:

- [project_context.md](project_context.md) for aims, scope, architecture, and current boundaries.
- [evolving_goals.md](evolving_goals.md) for active decisions and dated project direction.
- [segment_registry_contract.md](segment_registry_contract.md) for the locked Segments 0-3 project/folder/manifest contract.
- [download_package_inventory.md](download_package_inventory.md) for the installer/offline-package inventory and release packaging boundary.
- [module_map.md](module_map.md) for the current source ownership map and refactor direction.
- [loudness_calibration.md](loudness_calibration.md) for the Study 5 headphone/interface loudness calibration findings and policy direction.
- [looming_stimulus_generation_standard.md](looming_stimulus_generation_standard.md) for the current DynaSpace-derived golden standard for generated looming stimuli.
- [dashboard_gui_behavior.md](dashboard_gui_behavior.md) for current HTML dashboard edit/view-mode and downward-decision-propagation behavior.
- [audiotactile-paper-metadata-audit/README.md](audiotactile-paper-metadata-audit/README.md) for the standalone paper/PDF/supplement metadata extraction audit that is independent from GUI profile recreation.
- [agent_update_protocol.md](agent_update_protocol.md) for how to keep this folder current.
- [skills/html-dashboard-orchestrator/SKILL.md](skills/html-dashboard-orchestrator/SKILL.md) before making HTML dashboard or hosted-GitHub-Pages GUI changes.

## Project Summary

The repository is a public, reusable Python toolkit for audio-tactile peripersonal-space (PPS) experiments. It began as a cleaned and compartmentalized Study 5 replication tool and is evolving into a general Windows-ready PPS experiment designer/runner.

The toolkit currently centers on:

- stimulus generation for looming audio and tactile cues
- a Windows-first experiment runner with audio/tactile channel routing
- a standalone runner launcher with bounded participant dropdowns and explicit local audio-asset generation controls
- loopback WAV decoding for onset and response recovery
- deidentified sample-data analysis
- a stimulus/trial designer for configurable audio-tactile PPS paradigms
- preloadable published-study templates
- a tracked lightweight downloader package source plus a validated repo-shaped install payload contract
- a Qt runtime preflight that prevents packaging the runner without the Windows `qwindows.dll` platform plugin
- public-release safeguards that keep participant data, generated outputs, models, SOFA/HRIR files, and third-party assets out of Git
- a project-local skill workflow for safely changing the HTML dashboard as a local software orchestrator

## Agent Requirement

Every future AI agent should:

1. Read this folder before planning or editing.
2. Check whether the current chat changed aims, scope, GUI behavior, data schemas, runner behavior, tests, publication boundaries, or repo structure.
3. When changing the HTML dashboard, keep the packaged local dashboard and the online/static GitHub Pages dashboard synchronized in the same change set; update and verify both before finalizing.
4. Preserve the public domain and route contract in `agent_update_protocol.md`: `https://ppskit.qzz.io/` is the toolkit route, `/documentation` is documentation, `/download` is downloads, `https://georgefejer91.github.io/pps-kit/` is the GitHub Pages fallback, and the old `/peripersonal-space-toolkit/` Pages path should not be reintroduced.
5. Treat `segment_registry_contract.md` as authoritative for Segments 0-3 unless the user explicitly asks to revise that contract.
6. Preserve the tracked downloader package definition in `windows/installer_package_inventory.v1.json` and the single-file downloader/install-payload boundary in `download_package_inventory.md` when changing packaging.
7. When changing experiment-runner functionality, update and verify the packaged/local `PPSExperimentRunner.exe` path in the same change set so the installable runner carries the source behavior, not only the Python development entrypoint.
8. Update the relevant `For-AI/` files before finalizing substantive work.
9. State in the final response whether `For-AI/` was updated or why no update was needed.

Do not put secrets, participant data, generated artifacts, local absolute paths, or private notes in this folder.

## Global Publishing Rule

Every completed repository change must be committed and pushed to GitHub before finalizing. Keep commits scoped to the intended work and do not stage unrelated pre-existing worktree changes. HTML/dashboard GUI changes must keep the packaged local dashboard and the hosted/static GitHub Pages dashboard mutually synchronized: any change to one side requires the matching change to the other side in the same change set, followed by an immediate push so the website updates from the same source state.
