# Module Map

This is the compact navigation map for future agents. Read it after `For-AI/README.md` and before structural edits.

## Current Ownership

- Dashboard backend and Segment 0-6 materialization: `src/peripersonal_space_toolkit/dashboard_app.py`.
- Dashboard backend helper seams: `src/peripersonal_space_toolkit/dashboard_backend/`.
- Browser dashboard/static GitHub Pages surface: `src/peripersonal_space_toolkit/dashboard/`, root `index.html`, `.nojekyll`, `CNAME`.
- Loudness policy, SPL estimate metadata, dB/RMS helpers, final-active-window calibration rules, and standalone loudness-manifest helpers: `src/peripersonal_space_toolkit/loudness.py`.
- Shared stored-profile catalogue, runner memory, acquisition bridge, and output diary helpers: `profile_memory.py`.
- Runtime package preparation and participant playback: `session_runner.py`, `focus_app.py`, `focus_launch.py`, with runner-owned LabRecorder RCS subprocess capture isolated in `labrecorder_capture.py`.
- Participant tactile detection-threshold calibration: `tactile_calibration/` owns the `two_down_one_up_detection_threshold.v1` Output 3/4 assay, transient 44.1 kHz three-channel stimulus generation, adaptive-staircase/reversal metadata, response-window/ITI-jitter timing metadata, participant calibration report/CSV/latest-pointer persistence, and schema helpers; `focus_app.py` owns the native runner `Tactile Threshold` button, target-click interception, per-participant reload/application, and session-metadata handoff.
- Focus Mode phone companion and phone-transfer runtime: `runner_companion.py` owns the FastAPI/WebSocket token-gated LAN service, HTTP-safe bridge-error handling, v1/v2 QR payload helpers, token-gated setup/start/pause/resume/continue routes, and token-gated `/api/mobile/...` package routes; `mobile_phone_runtime.py` owns phone package list/manifest schemas, block WAV asset checksum export, CSV-derived phone cue/trial payloads, uploaded PC-copy artifact writing, and `phone_owned_session` manifest flags; `focus_app.py` owns the Qt-thread PC-control bridge, transfer-only `Send To Phone` bridge, snapshot/command state, mobile package access to active/sibling split part packages, separate mutually exclusive Pause/Resume controls, hidden internal close/stop cleanup, post-run timer responsiveness while the service is active, and Wi-Fi Direct availability messaging; `android/runner-companion/` owns the native Kotlin/Compose phone app, its two modes (`PC Runner Control` and `Run Experiment On Phone`), package sync/full-experiment phone runtime controls, phone-owned local artifact/ZIP export, and its landscape runner-confirmed cue/click timeline visualization with inline SOA and RT annotations. Android timeline scaling, annotation visibility, and density behavior lives in `TimelineLayoutModel.kt`; phone-runtime package parsing lives in `MobileRuntimeModels.kt`.
- Provisional Woojer tactile-drive latency compensation: `tactile_latency.py`, consumed by `session_runner.py` during participant/top-up block WAV preparation.
- Shared runner/dashboard profile memory and output-diary bridge: `runner_diary.py` now owns runner settings and diary helpers; future shared profile-catalogue code should live in a common Python seam consumed by both `dashboard_app.py` and `focus_app.py`, not separately in browser JS or runner UI code.
- Event, timing, and output evidence contracts: `timing_events.py`, `session_events.py`, `output_evidence.py`, `topup.py`.
- Optional LSL sender/receiver command acknowledgement helpers: `lsl_command_ack.py`, with real `pylsl` round-trip validation in `validation_protocols/scripts/run_lsl_command_ack_roundtrip.py`.
- Left-monitor companion emulator window placement: `windows/Set_Companion_Emulation_Layout.ps1` pins the packaged runner and Android emulator to `DISPLAY2` by default, can keep reapplying placement during launch, and raises windows with `SWP_NOACTIVATE` so validation stays visible without stealing the user's mouse/keyboard focus; `focus_app.py` also honors `PPS_FOCUS_VALIDATION_DISPLAY`, `PPS_FOCUS_VALIDATION_RUNNER_WIDTH`, and `PPS_FOCUS_VALIDATION_WINDOW_RECT` so windowed runner validation opens directly on that display. `PPS_FOCUS_VALIDATION_PARTICIPANT_RESPONSES_ONLY=1` keeps app-driven companion command tests from being preempted by validation auto-start/continue helpers.
- Published-study preload recreation gate: `profile_recreation.py`, `assets/preloads/`, `study_templates/`.
- Core paper-audit read API: `peripersonal_space_toolkit.paper_audit`.
- Behavioral PPS replication checks for collected/public derived CSVs:
  `mobile_pps_replication.py`, with the folder-capable validation helper in
  `validation_protocols/scripts/analyze_mobile_pps_replication.py`.
- Paper-audit acquisition/refresh tools: `tools/paper_metadata_parser/`.
- Tracked paper-audit memory and ledgers: `For-AI/audiotactile-paper-metadata-audit/`.
- Validation protocols and lab evidence scripts: `validation_protocols/`.

## Refactor Direction

Keep public imports stable while extracting:

- `dashboard_app.py` remains the compatibility facade for `create_app`, `DashboardController`, and `pps-dashboard`.
- Segment manifest validation should move from the backend monolith into manifest/segment modules.
- Runtime launch/session package work should move toward `runtime/` modules.
- Event and marker schemas should move toward `events/` modules.
- Browser JS should split only after backend/API seams are stable, and local packaged plus hosted/static assets must stay synchronized.

## Literature/Paper Audit Rule

The paper audit is a core pipeline, not a side report. It catalogs the needs, profiles, parameters, missing publication details, and toolkit-structure gaps across audio-tactile PPS studies so future implementations can be built from a growing knowledge base. Keep tracked audit files source-pointer-only; keep PDFs, supplements, extracted full text, screenshots, and local bundles ignored.
