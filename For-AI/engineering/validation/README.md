# Internal Validation Protocols

This folder contains internal lab stress-test protocols for validating PPS timing,
GUI-to-artifact traceability, LSL marker reliability, and hardware loopback
behavior. It is intentionally outside `packages/pps-runtime/src/peripersonal_space_toolkit/` and is
not part of the packaged experiment runtime.

Use these files to verify that the existing GUI, 3DTI render path, native runner,
event logs, LSL stream, and loopback tools behave as expected. Do not add a
console entry point for this folder unless the validation work becomes a real
product feature later.

## Output Boundary

Validation runs may generate recordings, CSVs, JSON reports, and screenshots.
Keep those under ignored local paths:

```text
artifacts/validation_runs/
local_data/validation_runs/
```

Do not commit participant recordings, local XDF files, generated WAVs, raw
LabRecorder output, or private hardware notes.

## Protocol Order

Run the protocols in this order when doing a full timing audit:

0. `protocols/00_dummy_3ch_channel_latency_validation.md`
1. `protocols/01_gui_to_stimulus_trace.md`
2. `protocols/02_audio_route_loopback_latency.md`
3. `protocols/03_session_event_logging.md`
4. `protocols/04_lsl_marker_reliability.md`
5. `protocols/05_emulated_mouse_click_timing.md`
6. `protocols/06_end_to_end_stress_matrix.md`
7. `protocols/07_one_block_actual_experimental_condition_validation.md`
8. `protocols/08_missed_trial_topup_stress.md`
9. `protocols/09_recording_layer_alignment_validation.md`
11. `protocols/11_exhaustive_emulated_participant_runner_stress_test.md`
12. `protocols/12_published_profile_recreation_interface_validation.md`

For a first hardware/data-collection confidence check, run protocol 0 before
using real experiment stimuli. For next-phase runner, latency, LSL, and
response validation, run protocol 7 on exactly one actual prepared
experimental block. Dummy pulse and fake-engine sessions are preflights only;
they are not the accepted evidence source for next-phase experimental claims.
Do not report new formal latency, channel-skew, response, or LSL/XDF
reliability numbers from synthetic-only runs once actual experimental block
validation has started.

Protocol 11 is the pre-participant operational stress matrix. It keeps the real
packaged Focus Mode / `SessionRunnerController` workflow under test while using
controlled emulated response plans to audit launch paths, session resolution,
stimulus assembly, response pairing, top-up behavior, capture options, output
analysis, and operator failure modes.

Protocol 12 is the published-profile recreation interface matrix. It verifies
that ready published preloads pass the Segment 0-4 profile gate, remain
read-only in the interface, materialize through local Segments 0-6, and produce
profile-local runner-handoff artifacts before a profile is treated as runnable
evidence.

## Scripts

Scripts are manual helpers, not public package APIs:

```powershell
.\For-AI/engineering/validation\scripts\run_audio_route_stress.ps1
.\For-AI/engineering/validation\scripts\run_loopback_calibration.ps1
python .\For-AI/engineering/validation\scripts\make_dummy_pulse_stimulus.py
python .\For-AI/engineering/validation\scripts\run_dummy_pulse_latency.py --device-query Komplete --record-asio-loopback
python .\For-AI/engineering/validation\scripts\run_dummy_pulse_latency.py --device-query Komplete --amplitude 0.02 --channel-amplitudes 1:0.0005,2:0.02,3:0.02 --record-asio-loopback --emit-lsl
python .\For-AI/engineering/validation\scripts\compare_dummy_pulse_recordings.py --run-dir artifacts\validation_runs\dummy_pulse_YYYYMMDD_HHMMSS
python .\For-AI/engineering/validation\scripts\diagnose_dummy_channel_route.py --run-dir artifacts\validation_runs\dummy_pulse_YYYYMMDD_HHMMSS
python .\For-AI/engineering/validation\scripts\run_dummy_output_route_sweep.py --device 31 --device-query Komplete --sweep-output-count 3
python .\For-AI/engineering/validation\scripts\run_dummy_output_route_sweep.py --device-query Komplete --amplitude 0.02 --channel-amplitudes 1:0.0005,2:0.02,3:0.02 --input-channels 6 --output-channels 3 --sweep-output-count 3
python .\For-AI/engineering/validation\scripts\run_dummy_output_route_sweep.py --device-query Komplete --input-channels 6 --output-channels 6 --sweep-output-count 6 --amplitude 0.05
python .\For-AI/engineering/validation\scripts\analyze_dummy_signal_levels.py --run-dir artifacts\validation_runs\dummy_output_route_sweep_YYYYMMDD_HHMMSS
python .\For-AI/engineering/validation\scripts\lsl_marker_probe.py --stream-name PPSMarkersV2 --duration-s 60
python .\For-AI/engineering/validation\scripts\reconcile_lsl_with_local_events.py --events-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\events.csv --lsl-markers-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\lsl_markers.csv --rich-lsl-probe-csv artifacts\validation_runs\lsl_probe_rich\lsl_marker_probe.csv --numeric-lsl-probe-csv artifacts\validation_runs\lsl_probe_numeric\lsl_marker_probe.csv --output-dir artifacts\validation_runs\lsl_reconciliation
python .\For-AI/engineering/validation\scripts\run_labrecorder_lsl_xdf_stress.py --output-dir artifacts\validation_runs\labrecorder_lsl_xdf_current
python .\For-AI/engineering/validation\scripts\run_mouse_response_timing_stress.py --enable-lsl --count 50 --interval-s 0.02
python .\For-AI/engineering/validation\scripts\compare_response_timing_strategies.py --events-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\events.csv --timing-qc-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\timing_qc.csv --rich-lsl-probe-csv artifacts\validation_runs\lsl_probe_rich\lsl_marker_probe.csv --output-dir artifacts\validation_runs\response_strategy_comparison
python .\For-AI/engineering/validation\scripts\run_session_runner_click_path_stress.py --count 25 --interval-s 0.02
python .\For-AI/engineering/validation\scripts\run_one_block_trial_runner_realtime_stress.py --output-dir artifacts\validation_runs\one_block_trial_runner_realtime_current
python .\For-AI/engineering/validation\scripts\run_topup_missed_trial_stress.py --output-dir artifacts\validation_runs\topup_missed_trial_stress_current
python .\For-AI/engineering/validation\scripts\run_trajectory_viewer_navigation_validation.py --output-dir artifacts\validation_runs\trajectory_viewer_navigation_current
python .\For-AI/engineering/validation\scripts\run_study5_end_to_end_ui_mouse_validation.py --packaged-standalone-app
python .\For-AI/engineering/validation\scripts\run_focus_runner_layout_validation.py --offscreen --output-dir artifacts\validation_runs\focus_runner_layout_current
python .\For-AI/engineering/validation\scripts\run_full_realtime_participant_emulation.py --participant-id P001 --mouse-backend pynput
python .\For-AI/engineering/validation\scripts\run_full_realtime_participant_emulation.py --participant-id P001 --mouse-backend pynput --audio-mode hardware --strict-study5-readiness
python .\For-AI/engineering/validation\scripts\run_full_realtime_participant_emulation.py --participant-id P001 --mouse-backend pynput --audio-mode hardware --validation-lane full-stack --external-labrecorder --strict-study5-readiness
python .\For-AI/engineering/validation\scripts\run_desktop_full_mock_rehearsal.py --desktop-output-parent "$env:USERPROFILE\Desktop" --session-name study_5_full_mock_rehearsal --participant-id P050 --runner-mode packaged --validation-lane full-stack --audio-mode hardware --mouse-backend pynput --wired-loopback output4-tactile-proxy --external-labrecorder --strict-study5-readiness --timeout-s 7200
python .\For-AI/engineering/validation\scripts\run_full_realtime_participant_emulation.py --runner-mode source --participant-id P001 --mouse-backend pynput --audio-mode hardware --strict-study5-readiness
python .\For-AI/engineering/validation\scripts\run_protocol11_controlled_response_matrix.py --output-dir artifacts\validation_runs\protocol11_controlled_response_matrix_current
python .\For-AI/engineering/validation\scripts\run_protocol11_capture_options_matrix.py --output-dir artifacts\validation_runs\protocol11_capture_options_matrix_current
python .\For-AI/engineering/validation\scripts\validate_protocol11_emulated_runner_artifacts.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS --response-plan artifacts\validation_runs\protocol11_response_plan.json
python .\For-AI/engineering/validation\scripts\audit_protocol11_study5_readiness.py --artifact-dir artifacts\validation_runs\full_study5_realtime_current --require-full-study5 --require-realtime
python .\For-AI/engineering/validation\scripts\run_profile_recreation_interface_matrix.py --output-dir artifacts\validation_runs\profile_recreation_interface_matrix_current
python .\For-AI/engineering/validation\scripts\run_ready_profile_runner_smoke.py --profile-set ready-published --output-dir artifacts\validation_runs\ready_profile_runner_smoke_current
python .\For-AI/engineering/validation\scripts\run_ready_profile_response_marker_loopback.py --smoke-report artifacts\validation_runs\ready_profile_runner_smoke_current\ready_profile_runner_smoke_report.json --output-dir artifacts\validation_runs\ready_profile_response_marker_loopback_current
python .\For-AI/engineering/validation\scripts\run_ready_profile_expected_contrast_audit.py --runner-smoke-report artifacts\validation_runs\ready_profile_runner_smoke_current\ready_profile_runner_smoke_report.json --output-dir artifacts\validation_runs\ready_profile_expected_contrast_audit_current
python .\For-AI/engineering/validation\scripts\run_focus_mode_click_path_stress.py --output-dir artifacts\validation_runs\focus_mode_click_path_current --count 10 --offscreen
python .\For-AI/engineering/validation\scripts\run_visible_runner_os_click_stress.py --output-dir artifacts\validation_runs\visible_runner_os_click_stress_current --count 10 --interval-s 0.05 --armed
python .\For-AI/engineering/validation\scripts\run_one_block_actual_condition_validation.py --run-setup-manifest local_data\dashboard_projects\0_study_project_registry\profile_pfeiffer_2018_lateral_perihead_left_to_right\6_experiment_run_setup\experiment_run_setup_manifest.json --device 31 --audio-gain 0.005 --tactile-gain 0.05
python .\For-AI/engineering/validation\scripts\validate_one_block_actual_condition_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
python .\For-AI/engineering/validation\scripts\compare_actual_block_loopback.py --session-dir artifacts\validation_runs\one_block_actual_condition_current\sessions\P001_YYYYMMDD_HHMMSS
python .\For-AI/engineering/validation\scripts\compare_recording_layers.py --session-dir artifacts\validation_runs\one_block_actual_condition_current\sessions\P001_YYYYMMDD_HHMMSS --output-dir artifacts\validation_runs\recording_layer_alignment_current
python .\For-AI/engineering/validation\scripts\compare_response_marker_loopback.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS --tactile-channel 3
python .\For-AI/engineering/validation\scripts\audit_pc_software_requirements.py
.\For-AI/engineering/validation\scripts\download_labrecorder.ps1
python .\For-AI/engineering/validation\scripts\emulate_mouse_clicks.py --count 10 --interval-s 0.5 --armed
python .\For-AI/engineering/validation\scripts\summarize_validation_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
python .\For-AI/engineering/validation\scripts\build_validation_evidence_audit.py --output-dir For-AI/engineering/validation\reports\evidence_audit
python .\For-AI/engineering/validation\scripts\analyze_mobile_pps_replication.py --input path\to\master_successful_participants.csv --output-dir artifacts\validation_runs\mobile_pps_replication_current
python .\For-AI/engineering/validation\scripts\analyze_mobile_pps_replication.py --input path\to\collected_pps_data_folder --output-dir artifacts\validation_runs\mobile_pps_replication_current
```

Hardware playback scripts default to amplitude `0.05` and refuse amplitudes
above `0.10`. If a channel is too quiet, adjust the physical patch, input gain,
or detection setup; do not raise the digital test tone into clipping. Equal
interface knob positions are not evidence of equal recorded levels. Use the
captured peak/SNR/correlation/clipping reports to balance the inputs.

Ready-profile runner smoke compacts per-profile generated WAV/session trees by
default after it records CSV/JSON/XDF evidence for downstream loopback and
expected-contrast audits. Pass `--keep-materialized` only when the full
generated session tree is the artifact under inspection and sufficient disk
space is available.

The full validation PC software checklist is tracked in
`docs/WINDOWS_PC_SOFTWARE_REQUIREMENTS.md`. The current lab install should use:

```powershell
python -m pip install -e ".[gui,web,lsl,validation]"
```

Vendor installers and LabRecorder binaries are kept out of Git. The LabRecorder
downloader fetches the official Windows release asset into ignored
`local_data/software_installers/` and extracts it into ignored
`local_data/software_tools/`.

## Interpretation

Separate these quantities in every report:

- GUI/artifact agreement: whether GUI settings became the same rendered and
  scheduled stimulus.
- Software scheduling: whether event logs match expected block sample timing.
- LSL reliability: whether LSL received all actual markers with stable arrival
  behavior, and whether rich LSL event metadata reconciles exactly with local
  `events.csv`/`lsl_markers.csv`.
- External XDF preservation: whether runner-owned LabRecorder records both
  `PPSMarkersV2` and `PPSTriggerCodes` without missing, duplicate, or
  mismatched markers, after the runner has verified the session LSL source IDs
  and before playback begins.
- Focus Mode setup gate: whether `Submit setup` validates participant metadata,
  freezes pre-run capture choices, prepares the session/controller layer, and
  creates the session-lifetime LSL outlets before `Start Run` can enable
  playback.
- Visible OS mouse delivery: full-stack rehearsals should report the requested
  mouse backend and any recovery backend. A run that relies on Qt/qtest recovery
  can prove data-shape and capture completeness, but it is not final visible
  OS-click evidence.
- Electrical latency: output-to-input timing from direct loopback calibration.
- Single-file channel routing: whether one 3-channel WAV independently reaches
  left Sennheiser, right Sennheiser, and Woojer/tactile output paths.
- Audio-tactile skew: whether channel 3 stays synchronized with channels 1/2.
- Response-marker delay: mouse event to tactile-channel response-marker timing.
- Response strategy comparison: local mouse log versus rich LSL mouse sample
  timestamp versus LSL probe arrival timing.
- Session runner click path: whether `SessionRunnerController.log_click()`
  triggers linked callback-derived response markers during active playback.
- PySide Focus Mode click path: whether the native Focus Mode app shell's large
  participant response target dispatches clicks into the runner controller. The
  fake-controller stress is a UI-signal preflight and does not replace the
  one-block actual-condition evidence gate.
- One-block realtime runner output: whether one Segment 5/6-style block can be
  prepared, played on the runner timeline with jittered simulated responses,
  and immediately yield `events.csv`, loadable `events.xdf`, `lsl_markers.csv`,
  `trigger_dictionary.json`, timing QC, and `*_analysis_ready_trials.csv`.
  This remains a software preflight when it uses the fake audio engine.
- Mobile-style PPS behavioral replication: whether collected trial-level PPS
  data show the basic smartphone/DynaSpace-style behavioral assumptions:
  acceptable hit/catch/anticipation integrity, faster audio-tactile responses
  than matched tactile-only baseline, SOA/distance-dependent approach trends,
  and defensible or non-defensible sigmoid boundary fits. The helper
  `analyze_mobile_pps_replication.py` can analyze one CSV or scan a collection
  folder for OSF-style `master_successful_participants.csv`, pps-kit
  `analysis_ready_trials.csv`, `final_trial_outcomes.csv`, or participant
  `*_trials.csv` files. This is a behavioral data-shape check; it does not
  validate hardware timing, raw WAV decoding, LSL/XDF persistence, or physical
  tactile onset.
- One-block actual-condition runner evidence: whether an actual Segment 5/6
  prepared experimental block, administered as one block through the runner,
  yields complete sample-exact event logs, XDF/LSL mirror outputs, trigger
  dictionary, local audio-evidence WAV when selected, and an immediately
  analyzable `*_analysis_ready_trials.csv`. This is the required next-phase
  evidence gate.
- Recording-layer alignment: whether one actual-condition block's physical
  loopback WAV, local digital output evidence WAV, and callback-derived
  LSL/event records agree on the same sample timeline. Physical loopback is the
  temporary validation reference; the local audio evidence WAV and LSL marker
  records are the normal experiment-time safety layers.
- Dashboard-to-Focus-Mode handoff: the normal HTML dashboard Segment 6 launch
  path prepares/reuses a native participant session package and starts
  packaged `PPSExperimentRunner.exe --session-manifest ...`
  when available. Focus Mode owns participant metadata, standard LSL/internal
  XDF mirrors, analysis CSVs, and optional local audio evidence WAV capture;
  `events.csv` remains always on. The retired legacy Tk runner is historical
  validation coverage only, not an operator launch path.
- Focus Mode adaptive layout and keyboard controls: whether the native runner
  fits the current PC screen plus compact, laptop, desktop, and wide scenarios
  without clipped text, overlapping controls, or unusable splitters. The layout
  validation harness consumes the runner's embedded `layout_validation_snapshot`
  and `layout_validation_failures()` methods, checks that `Experiment Control`
  starts at the adaptive profile height and spans the lower workspace, verifies
  constrained-screen operator tabs versus resizable splitters, captures
  nonblank screenshots, and confirms the automation shortcut map for
  start/continue, pause/resume, stop, close, part selection, and top-up preview.
- Exhaustive emulated-participant runner stress: whether the packaged Focus
  Mode / `SessionRunnerController` workflow survives controlled launch,
  cache/prewarm, stimulus, response-boundary, instruction, top-up, capture,
  analysis, LSL/trigger, and operator-failure scenarios with emulated response
  plans. `run_protocol11_controlled_response_matrix.py` is the deterministic
  boundary-response scenario: it prepares a real Segment 5/6 session package,
  runs `SessionRunnerController`, exercises instruction target clicks, catch
  and baseline rows, out-of-target and double clicks, +99 ms/+100 ms/+1300 ms/
  >1300 ms response pairing, and a click exactly at the next `trial_start`, then
  feeds the resulting session to the artifact gate. `run_protocol11_capture_options_matrix.py`
  is the local output-policy gate for capture variants: it verifies events-only,
  internal-XDF-only, analysis-without-XDF/LSL, marker-mirror-only, and standard
  local-recording-enabled sessions. `validate_protocol11_emulated_runner_artifacts.py`
  is the offline artifact gate for completed scenarios: it consumes a session
  folder and response plan keyed by `trial_uid`, then verifies the written
  WAV/manifests, events, timing QC, analysis CSVs, marker mirrors, trigger
  dictionary, top-up files, and declared capture options.
  `audit_protocol11_study5_readiness.py` is the higher-level Study 5 evidence
  aggregator for packaged realtime runs: it parses `events.xdf` and
  `lsl_markers.xdf`, reconciles event and marker CSV layers, verifies
  `trigger_dictionary.json`, checks nonblank Focus Mode screenshots, audits
  block WAV geometry and manifest sample columns, checks every per-block
  Komplete ASIO 4-channel local audio-evidence WAV/sidecar, generates the
  LSL/XDF/audio reconciliation report when needed, generates local
  audio-evidence response-marker recovery when needed, verifies the analysis
  CSV family, checks that selected response IDs are unique logged mouse events
  even when raw playback clicks include double/random extras, audits top-up
  rescues against the original missed-trial plan, and reports RT tolerance
  against the emulated click plan. For visible OS-click backends
  (`pyautogui`, `pynput`, `win32`), RT tolerance is distribution-aware:
  controller/QTest paths must satisfy the strict max tolerance, while OS-click
  paths must keep p95 within the strict tolerance and max within the bounded
  OS-click tolerance reported by the audit. The audit reports whether the
  artifact is a full Study 5 realtime run or only a scoped rehearsal. The
  final Study 5 command is
  `run_full_realtime_participant_emulation.py --audio-mode hardware --strict-study5-readiness`;
  strict mode refuses fake audio and refuses disabling LSL, internal XDF, or
  local audio-evidence recording. If the local packaged exe is blocked by
  endpoint protection, `--runner-mode source` may be used as an interim
  hardware/capture diagnostic through `apps/runner/launchers/focus_runner_entry.py`, but it
  does not satisfy the packaged-runner launch requirement. If Komplete ASIO
  device indices are unstable across processes, confirm the current 4-channel
  route with `pps-audio-stress --device-query "Komplete Audio ASIO" --dry-run
  --channels 4` and pass that index with `--audio-device-index N`; the harness
  forwards it as `PPS_AUDIO_DEVICE_INDEX`. This is
  pre-participant operational evidence, not hardware latency, Woojer
  mechanical-onset, or scientific PPS evidence.
- Published-profile recreation interface matrix: whether ready published
  profiles can be selected through the preload/profile path, validated against
  `profile_recreation_status.json`, kept read-only, materialized through
  local Segments 0-6, and converted into runner-handoff artifacts without
  writing generated outputs under `assets/preloads/`. This is a parameter and
  interface recreation gate; it is not a claim to use original author stimuli
  or to prove hardware timing.
- Actual-block direct loopback evidence: whether the same actual one-block
  session's source block WAV and direct electrical capture recover stable
  channel alignment and paired inter-channel skew without clipping. Absolute
  capture alignment includes capture lead-in; inter-channel skew is the main
  synchronization estimate.
- Visible runner OS-click path: whether armed OS clicks delivered to the
  retired visible Tk target become in-target `mouse_click` events with linked
  `response_marker_start` markers. This preserves historical regression
  evidence for the click/marker timing path while Focus Mode is the public
  runner UI.
- Response-marker loopback recovery: whether tactile-channel pulses in the
  physical recording recover logged `response_marker_start` sample indices after
  fitting the recording/hardware offset.
- WASAPI boundary: WASAPI loopback is not a core acceptance strategy for the
  ASIO multichannel route because ASIO playback can bypass the Windows endpoint
  that WASAPI records.
- Deferred mechanical extension: Woojer mechanical vibration onset is outside
  the current electrical validation because the Woojer is not physically in the
  loop. Add a vibration sensor/contact microphone only when that later question
  is ready to be measured.

Current accepted electrical baseline: the channel-scaled dummy run used
`--channel-amplitudes 1:0.0005,2:0.02,3:0.02`, recovered 5/5 direct-loopback
pulses on all three channels, and measured channel latencies of 33.605,
33.583, and 33.605 ms. Left/right skew was 0.023 +/- 0.000 ms, and
tactile/audio electrical skew was 0.011 +/- 0.000 ms. WASAPI initialized but
recorded no data for this ASIO multichannel route, so it has been removed from
the core validation strategy; the external LSL probe received 5/5 dummy
markers.

Current accepted actual-condition one-block run:
`artifacts/validation_runs/one_block_actual_condition_current/sessions/P001_20260612_182812`.
It used one real prepared Pfeiffer-style Segment 5/6 block through Komplete
ASIO with full-duplex direct capture, conservative gains
`audio_gain=0.005` and `tactile_gain=0.05`, 20 simulated post-tactile clicks,
146 loadable XDF samples, 146 LSL mirror rows, 20 analysis-ready response rows,
and an unclipped 3-channel direct capture. Actual-block loopback comparison
estimated left/right skew at -0.023 +/- 0.000 ms and tactile-minus-audio-mean
skew at -0.079 +/- 0.000 ms over usable correlated trial segments. Absolute
capture alignment includes validation capture lead-in, so use paired
inter-channel skew for synchronization claims.

If validation reveals missing observability, document the gap first. Only change
runtime code when the gap exposes a real experiment-correctness issue.

## Living Report

Record validated methods, measured results, and explicit measurement boundaries
in:

```text
For-AI/engineering/validation/reports/latency_reliability_validations.tex
```

This report is the accumulation point for dummy 3-channel routing, direct
loopback, LSL/XDF, mouse-click, and response-marker validation evidence.
Use the evidence audit as an internal completeness checklist; keep exploratory
route/level setup captures out of publication-facing latency/skew estimates
unless they become the final accepted all-channel baseline.

Treat the LaTeX file as having two phases. During validation, it can function
as a lab ledger and checklist so intermediate status is not lost. Before using
it as the scientific end report, rewrite it as a conclusions-first summary:
keep validated methods, accepted evidence, measured results, and scope-setting
measurement boundaries; remove operational todo/progress language from the main
narrative or move it to an internal appendix.
