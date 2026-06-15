# Internal Validation Protocols

This folder contains internal lab stress-test protocols for validating PPS timing,
GUI-to-artifact traceability, LSL marker reliability, and hardware loopback
behavior. It is intentionally outside `src/peripersonal_space_toolkit/` and is
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

## Scripts

Scripts are manual helpers, not public package APIs:

```powershell
.\validation_protocols\scripts\run_audio_route_stress.ps1
.\validation_protocols\scripts\run_loopback_calibration.ps1
python .\validation_protocols\scripts\make_dummy_pulse_stimulus.py
python .\validation_protocols\scripts\run_dummy_pulse_latency.py --device-query Komplete --record-asio-loopback
python .\validation_protocols\scripts\run_dummy_pulse_latency.py --device-query Komplete --amplitude 0.02 --channel-amplitudes 1:0.0005,2:0.02,3:0.02 --record-asio-loopback --emit-lsl
python .\validation_protocols\scripts\compare_dummy_pulse_recordings.py --run-dir artifacts\validation_runs\dummy_pulse_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\diagnose_dummy_channel_route.py --run-dir artifacts\validation_runs\dummy_pulse_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\run_dummy_output_route_sweep.py --device 31 --device-query Komplete --sweep-output-count 3
python .\validation_protocols\scripts\run_dummy_output_route_sweep.py --device-query Komplete --amplitude 0.02 --channel-amplitudes 1:0.0005,2:0.02,3:0.02 --input-channels 6 --output-channels 3 --sweep-output-count 3
python .\validation_protocols\scripts\run_dummy_output_route_sweep.py --device-query Komplete --input-channels 6 --output-channels 6 --sweep-output-count 6 --amplitude 0.05
python .\validation_protocols\scripts\analyze_dummy_signal_levels.py --run-dir artifacts\validation_runs\dummy_output_route_sweep_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\lsl_marker_probe.py --stream-name PPSMarkersV2 --duration-s 60
python .\validation_protocols\scripts\reconcile_lsl_with_local_events.py --events-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\events.csv --lsl-markers-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\lsl_markers.csv --rich-lsl-probe-csv artifacts\validation_runs\lsl_probe_rich\lsl_marker_probe.csv --numeric-lsl-probe-csv artifacts\validation_runs\lsl_probe_numeric\lsl_marker_probe.csv --output-dir artifacts\validation_runs\lsl_reconciliation
python .\validation_protocols\scripts\run_labrecorder_lsl_xdf_stress.py --output-dir artifacts\validation_runs\labrecorder_lsl_xdf_current
python .\validation_protocols\scripts\run_mouse_response_timing_stress.py --enable-lsl --count 50 --interval-s 0.02
python .\validation_protocols\scripts\compare_response_timing_strategies.py --events-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\events.csv --timing-qc-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\timing_qc.csv --rich-lsl-probe-csv artifacts\validation_runs\lsl_probe_rich\lsl_marker_probe.csv --output-dir artifacts\validation_runs\response_strategy_comparison
python .\validation_protocols\scripts\run_session_runner_click_path_stress.py --count 25 --interval-s 0.02
python .\validation_protocols\scripts\run_one_block_trial_runner_realtime_stress.py --output-dir artifacts\validation_runs\one_block_trial_runner_realtime_current
python .\validation_protocols\scripts\run_topup_missed_trial_stress.py --output-dir artifacts\validation_runs\topup_missed_trial_stress_current
python .\validation_protocols\scripts\run_study5_end_to_end_ui_mouse_validation.py --packaged-standalone-app
python .\validation_protocols\scripts\run_full_realtime_participant_emulation.py --participant-id P001 --mouse-backend pynput
python .\validation_protocols\scripts\run_protocol11_controlled_response_matrix.py --output-dir artifacts\validation_runs\protocol11_controlled_response_matrix_current
python .\validation_protocols\scripts\run_protocol11_capture_options_matrix.py --output-dir artifacts\validation_runs\protocol11_capture_options_matrix_current
python .\validation_protocols\scripts\validate_protocol11_emulated_runner_artifacts.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS --response-plan artifacts\validation_runs\protocol11_response_plan.json
python .\validation_protocols\scripts\run_focus_mode_click_path_stress.py --output-dir artifacts\validation_runs\focus_mode_click_path_current --count 10 --offscreen
python .\validation_protocols\scripts\run_visible_runner_os_click_stress.py --output-dir artifacts\validation_runs\visible_runner_os_click_stress_current --count 10 --interval-s 0.05 --armed
python .\validation_protocols\scripts\run_one_block_actual_condition_validation.py --run-setup-manifest local_data\dashboard_projects\0_study_project_registry\profile_pfeiffer_2018_lateral_perihead_left_to_right\6_experiment_run_setup\experiment_run_setup_manifest.json --device 31 --audio-gain 0.005 --tactile-gain 0.05
python .\validation_protocols\scripts\validate_one_block_actual_condition_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\compare_actual_block_loopback.py --session-dir artifacts\validation_runs\one_block_actual_condition_current\sessions\P001_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\compare_recording_layers.py --session-dir artifacts\validation_runs\one_block_actual_condition_current\sessions\P001_YYYYMMDD_HHMMSS --output-dir artifacts\validation_runs\recording_layer_alignment_current
python .\validation_protocols\scripts\compare_response_marker_loopback.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS --tactile-channel 3
python .\validation_protocols\scripts\audit_pc_software_requirements.py
.\validation_protocols\scripts\download_labrecorder.ps1
python .\validation_protocols\scripts\emulate_mouse_clicks.py --count 10 --interval-s 0.5 --armed
python .\validation_protocols\scripts\summarize_validation_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\build_validation_evidence_audit.py --output-dir validation_protocols\reports\evidence_audit
```

Hardware playback scripts default to amplitude `0.05` and refuse amplitudes
above `0.10`. If a channel is too quiet, adjust the physical patch, input gain,
or detection setup; do not raise the digital test tone into clipping. Equal
interface knob positions are not evidence of equal recorded levels. Use the
captured peak/SNR/correlation/clipping reports to balance the inputs.

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
- External XDF preservation: whether LabRecorder records both `PPSMarkersV2`
  and `PPSTriggerCodes` without missing, duplicate, or mismatched markers.
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
- Exhaustive emulated-participant runner stress: whether the packaged Focus
  Mode / `SessionRunnerController` workflow survives controlled launch,
  cache/prewarm, stimulus, response-boundary, instruction, top-up, capture,
  analysis, LSL/trigger, and operator-failure scenarios with emulated response
  plans. `run_protocol11_controlled_response_matrix.py` is the deterministic
  boundary-response scenario: it prepares a real Segment 5/6 session package,
  runs `SessionRunnerController`, exercises instruction target clicks, catch
  and baseline rows, out-of-target and double clicks, +99 ms/+100 ms/+3.0 s/
  >3.0 s response pairing, and a click exactly at the next `trial_start`, then
  feeds the resulting session to the artifact gate. `run_protocol11_capture_options_matrix.py`
  is the local output-policy gate for capture variants: it verifies events-only,
  internal-XDF-only, analysis-without-XDF/LSL, marker-mirror-only, and standard
  local-recording-enabled sessions. `validate_protocol11_emulated_runner_artifacts.py`
  is the offline artifact gate for completed scenarios: it consumes a session
  folder and response plan keyed by `trial_uid`, then verifies the written
  WAV/manifests, events, timing QC, analysis CSVs, marker mirrors, trigger
  dictionary, top-up files, and declared capture options. This is
  pre-participant operational evidence, not hardware latency, Woojer
  mechanical-onset, or scientific PPS evidence.
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
validation_protocols/reports/latency_reliability_validations.tex
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
