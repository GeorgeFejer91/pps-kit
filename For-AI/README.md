# For-AI Project Memory

This folder is the required starting point for AI agents working on the Peripersonal Space Toolkit.

Read this file before modifying the repository. Then read:

- [project_context.md](project_context.md) for aims, scope, architecture, and current boundaries.
- [evolving_goals.md](evolving_goals.md) for active decisions and dated project direction.
- [segment_registry_contract.md](segment_registry_contract.md) for the locked Segments 0-3 project/folder/manifest contract.
- [agent_update_protocol.md](agent_update_protocol.md) for how to keep this folder current.
- [skills/html-dashboard-orchestrator/SKILL.md](skills/html-dashboard-orchestrator/SKILL.md) before making HTML dashboard or hosted-GitHub-Pages GUI changes.

## Project Summary

The repository is a public, reusable Python toolkit for audio-tactile peripersonal-space (PPS) experiments. It began as a cleaned and compartmentalized Study 5 replication tool and is evolving into a general Windows-ready PPS experiment designer/runner.

The toolkit currently centers on:

- stimulus generation for looming audio and tactile cues
- a Windows-first experiment runner with audio/tactile channel routing
- loopback WAV decoding for onset and response recovery
- deidentified sample-data analysis
- a stimulus/trial designer for configurable audio-tactile PPS paradigms
- preloadable published-study templates
- public-release safeguards that keep participant data, generated outputs, models, SOFA/HRIR files, and third-party assets out of Git
- a project-local skill workflow for safely changing the HTML dashboard as a local software orchestrator

## Agent Requirement

Every future AI agent should:

1. Read this folder before planning or editing.
2. Check whether the current chat changed aims, scope, GUI behavior, data schemas, runner behavior, tests, publication boundaries, or repo structure.
3. When changing the HTML dashboard, keep the packaged local dashboard and the online/static GitHub Pages dashboard synchronized in the same change set; update and verify both before finalizing.
4. Treat `segment_registry_contract.md` as authoritative for Segments 0-3 unless the user explicitly asks to revise that contract.
5. Update the relevant `For-AI/` files before finalizing substantive work.
6. State in the final response whether `For-AI/` was updated or why no update was needed.

Do not put secrets, participant data, generated artifacts, local absolute paths, or private notes in this folder.
