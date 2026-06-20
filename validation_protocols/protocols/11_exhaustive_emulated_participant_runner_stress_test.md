# Protocol 11: Exhaustive Emulated-Participant Runner Stress Test

## Purpose

Build the next validation checklist around controlled emulated responses while
still running the real Focus Mode / `SessionRunnerController` workflow. The
goal is to prove runner behavior, data logging, analysis pairing, top-up logic,
and operational UI control before asking a real participant to trust the
session.

## Scope

This is an internal operational stress protocol. It validates the packaged
runner, Focus Mode controls, session-package resolution, event scheduling,
response pairing, top-up handling, output writing, LSL/trigger behavior, and
analysis products under scripted participant behavior.

Use non-participant IDs and ignored validation folders only. Store outputs under
`artifacts/validation_runs/` or `local_data/validation_runs/`; do not commit
session folders, generated WAVs, XDF files, screenshots, or private hardware
notes.

Passing this protocol does not prove perception, fatigue, Woojer mechanical
onset, participant comprehension, or scientific PPS interpretability. Hardware
timing claims still require the actual-condition and loopback protocols.

## Validation Lanes

Protocol 11 now has two named lanes so software-only evidence cannot be
mistaken for final-condition evidence:

- `software-only`: runs the packaged Focus Mode workflow with
  `validation-realtime` audio. It is useful for UI survival, top-up logic,
  event/analysis pairing, and output-shape checks on machines without the
  lab audio route. It cannot prove Study 5 final readiness.
- `full-stack`: runs packaged Focus Mode with the normal hardware ASIO audio
  path, standard capture enabled, local audio-evidence WAVs, XDF/LSL outputs,
  trigger dictionary, visible OS mouse-click backend, and the strict Study 5
  readiness audit. This is the lane for final-condition pre-participant
  validation.

The response-marker invariant belongs to the full-stack lane: every in-playback
mouse click must be logged as `mouse_click`, paired to one `response_marker_start`,
and recoverable as a short tactile-channel pulse in the runtime
`*_audio_evidence.wav`. The precomputed `blocks/Block_*.wav` files are
stimulus-only WAVs and are not expected to contain response-click markers.

## Existing Harnesses

Use the existing scripts where they already cover part of the matrix:
replace `P001` with an unused planned validation ID from the selected run setup.

```powershell
python .\validation_protocols\scripts\run_full_realtime_participant_emulation.py `
  --participant-id P001 `
  --mouse-backend pynput `
  --validation-lane software-only `
  --audio-mode validation-realtime `
  --standard-capture

python .\validation_protocols\scripts\run_study5_end_to_end_ui_mouse_validation.py `
  --packaged-standalone-app

python .\validation_protocols\scripts\run_focus_runner_layout_validation.py `
  --offscreen `
  --output-dir artifacts\validation_runs\focus_runner_layout_current

python .\validation_protocols\scripts\run_one_block_actual_condition_validation.py `
  --run-setup-manifest local_data\dashboard_projects\0_study_project_registry\profile_pfeiffer_2018_lateral_perihead_left_to_right\6_experiment_run_setup\experiment_run_setup_manifest.json `
  --device 31 `
  --audio-gain 0.0005 `
  --tactile-gain 0.02

python .\validation_protocols\scripts\run_topup_missed_trial_stress.py `
  --output-dir artifacts\validation_runs\topup_missed_trial_stress_current
```

The final Study 5 pre-participant gate must use the normal ASIO/audio-evidence
path, not the validation fake-audio shortcut. Run it with hardware audio,
standard capture, and the strict readiness audit enabled:

```powershell
python .\validation_protocols\scripts\run_full_realtime_participant_emulation.py `
  --participant-id P001 `
  --mouse-backend pynput `
  --validation-lane full-stack `
  --audio-mode hardware `
  --strict-study5-readiness
```

For a full operator rehearsal that creates a fresh Desktop acquisition folder,
preloads Study 5 participant `P050`, turns on the output-4/Input-4 tactile proxy,
runs the packaged runner under full-stack conditions, and asks the runner to own
one continuous external LabRecorder XDF subprocess, use:

```powershell
python .\validation_protocols\scripts\run_desktop_full_mock_rehearsal.py `
  --desktop-output-parent "$env:USERPROFILE\Desktop" `
  --session-name study_5_full_mock_rehearsal `
  --profile study5_box_breathing_pps `
  --participant-id P050 `
  --runner-mode packaged `
  --validation-lane full-stack `
  --audio-mode hardware `
  --mouse-backend pynput `
  --wired-loopback output4-tactile-proxy `
  --external-labrecorder `
  --strict-study5-readiness `
  --timeout-s 7200
```

This rehearsal script writes its reports under
`Experiment_context_folder_DO_NOT_DELETE/validation_reports/mock_rehearsal_*`
inside the Desktop acquisition root. LabRecorder is intentionally continuous
for the whole session and is started by `SessionRunnerController` only after the
session `PPSMarkersV2` and `PPSTriggerCodes` LSL source IDs resolve. The Focus
Mode setup gate submits mock participant metadata first, which prepares the
session/controller layer and creates the LSL outlets before `Start Run` can be
clicked. Playback is held until the LabRecorder RCS child process is running;
block identity is reconstructed from marker fields rather than by restarting
external recording per block. The
rehearsal report also writes `cross_stream_reconciliation_report.json/md`,
which summarizes strict readiness CSV/internal-XDF/audio-evidence/RT checks,
the continuous external XDF comparison, and wired-loopback inventory.
If the focus validation report shows a backend such as `pynput+qtest_recovery`
or `win32+qtest_recovery`, treat the artifact as data-shape/capture evidence
only. Final full-stack OS-click readiness requires the requested visible OS
mouse backend to be observed without Qt recovery.

After the rehearsal completes, run the reusable final drift gate on the Desktop
acquisition root:

```powershell
python .\validation_protocols\scripts\audit_full_session_wired_lsl_xdf_drift.py `
  --rehearsal-root "$env:USERPROFILE\Desktop\study_5_full_mock_rehearsal_YYYYMMDD_HHMMSS"
```

The final Study 5 automated readiness rule treats the Output-4-to-Input-4
tactile proxy as the hardwired timing reference. The gate must detect every
`tactile_onset` pulse, keep external XDF vs local LSL timestamps within
0.1 ms, keep per-block tactile peak residual p95 <= 1 ms and max <= 2 ms, and
show no adjacent tactile step > 2 ms. Response-marker recovery is decided from
runtime digital audio evidence (`response_marker_loopback_report.json`) rather
than from the weak hardwired response-marker peak metric; hardwired
response-marker peak variation is informational only when digital recovery
detects all response-marker pulses. This gate still does not measure Woojer
mechanical vibration onset or human behavioral validity.

If the local packaged executable is quarantined or blocked by endpoint
protection, use source mode only as an interim hardware/capture diagnostic:

```powershell
python .\validation_protocols\scripts\run_full_realtime_participant_emulation.py `
  --runner-mode source `
  --participant-id P001 `
  --mouse-backend pynput `
  --validation-lane full-stack `
  --audio-mode hardware `
  --strict-study5-readiness
```

Source mode runs the same Focus Mode and `SessionRunnerController` code through
`windows/focus_runner_entry.py`, but it does not satisfy the packaged-runner
launch requirement.

If `sounddevice` enumeration is unstable across processes, pass the currently
verified Komplete ASIO output index with `--audio-device-index N`. The harness
forwards this as `PPS_AUDIO_DEVICE_INDEX`; use it only after confirming the
index with `pps-audio-stress --device-query "Komplete Audio ASIO" --dry-run
--channels 4`.

Run the deterministic response-boundary matrix before the broader packaged or
hardware-backed scenarios. It prepares a real Segment 5/6-style session package,
runs `SessionRunnerController`, exercises instruction target double-clicks,
catch and baseline rows, in-playback response markers, and exact response
pairing boundaries, then automatically runs the offline artifact gate:

```powershell
python .\validation_protocols\scripts\run_protocol11_controlled_response_matrix.py `
  --output-dir artifacts\validation_runs\protocol11_controlled_response_matrix_current
```

Run the capture-options matrix to verify the runner's durable output policies
across events-only, internal-XDF-only, analysis-without-XDF/LSL,
marker-mirror-only, and standard local-recording-enabled sessions:

```powershell
python .\validation_protocols\scripts\run_protocol11_capture_options_matrix.py `
  --output-dir artifacts\validation_runs\protocol11_capture_options_matrix_current
```

After each scenario writes a real runner session folder, run the offline
Protocol 11 artifact gate with the scenario's controlled response plan:

```powershell
python .\validation_protocols\scripts\validate_protocol11_emulated_runner_artifacts.py `
  --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS `
  --response-plan artifacts\validation_runs\protocol11_response_plan.json `
  --output-dir artifacts\validation_runs\protocol11_artifact_audit_current
```

For Study 5 participant-readiness claims, aggregate the packaged-runner
evidence folder with the Study 5 readiness audit. Use the strict flags for the
final gate; software-only artifacts can pass their own lane while still
reporting `final_condition_ready=false`. The full realtime harness writes the
launch/preparation reports and invokes this audit automatically when
`--validation-lane full-stack` or `--strict-study5-readiness` is set.

```powershell
python .\validation_protocols\scripts\audit_protocol11_study5_readiness.py `
  --artifact-dir artifacts\validation_runs\full_study5_realtime_current `
  --require-full-study5 `
  --require-realtime
```

The Study 5 readiness audit separates raw click logging from analysis-selected
responses. All in-playback clicks should remain locally logged and paired to
response markers, including extra double/random clicks, but analysis/top-up
selection must use unique logged `click_event_id` values and must match the
planned standard clicks plus approved top-up attempts. For controller and
QTest-style deterministic backends, RT errors must satisfy the strict maximum
tolerance. For visible OS-click backends (`pyautogui`, `pynput`, `win32`), RT
matching is distribution-aware: p95 must remain within the strict tolerance,
and the maximum outlier must remain within the audit's bounded OS-click
tolerance.

The response plan may be JSON or CSV. The minimum plan is keyed by
`trial_uid`; JSON plans may also declare expected capture options,
instruction slots, instruction-click actions, top-up behavior, and operator
failure-mode expectations.

When a checklist item has no dedicated harness yet, record it as a missing
automation gap before changing runtime code. Add runner code only when the gap
exposes experiment-correctness risk, missing observability, or an operator
failure mode.

## Stress-Test Checklist

### Launch, Session, And Package Resolution

- [ ] Launch the packaged runner via explicit `--session-manifest`, standalone
  profile launcher, latest-session resume, and dashboard Segment 6 handoff.
- [ ] Verify participant selection uses only planned IDs and rejects out-of-plan
  IDs before materialization.
- [ ] Confirm generated session paths, `session_manifest.json`,
  `session_metadata.json`, block WAVs, block manifests, and state pointers all
  resolve under writable `local_data/...`.
- [ ] Test prepared-session queue behavior: cache hit, stale fingerprint
  invalidation, next-participant prewarm, and no auto-start.
- [ ] Repeat after app restart and Windows reboot to catch resume/state bugs.

### Runner UI Geometry And Controls

- [ ] Verify the Focus Mode window renders inside the available desktop area at
  constrained, compact, standard, and wide monitor sizes, including native
  Windows DPI behavior and offscreen/headless validation.
- [ ] Confirm the Experiment Control panel starts at the profile-defined height,
  remains resizeable, spans the lower workspace, and never collapses the CLICK
  target, response buttons, output summary, block plan, timeline, or progress
  controls.
- [ ] Confirm Data Logging and Experiment Settings use two columns on screens
  with enough width, fall back to stacked layout only on genuinely narrow
  screens, and keep full details available through tooltips when compact text
  is used.
- [ ] Capture and inspect screenshots for every visual/layout decision; numeric
  geometry checks alone are not sufficient for readiness.
- [ ] Exercise keyboard shortcuts for automation: Space/Return/Enter
  start/continue, Ctrl+P pause/resume, Ctrl+Shift+S stop, Alt+1/Alt+2 part
  selection, Ctrl+T top-up preview, and Ctrl+W close.

### Stimulus Assembly

- [ ] For every assembled block, verify 3-channel geometry, sample rate,
  channel count, duration, and PCM integrity.
- [ ] Recompute `Trial_Start_Sample`, `Looming_Onset_Sample`,
  `Tactile_Onset_Sample`, `Response_Window_Onset_Sample`, and
  `Trial_End_Sample` from the manifest.
- [ ] Confirm catch trials have no tactile channel cue, baseline trials have a
  tactile cue, and audio-tactile trials preserve requested SOAs.
- [ ] Validate row-order invariants across Study 5 inhale/exhale structure and
  at least one non-Study-5 profile.
- [ ] Force missing WAV, hash mismatch, mixed sample-rate, and cache-corruption
  cases; the runner should fail clearly before playback.

### Timing And Event Schedule

- [ ] Every block emits `audio_sample_zero`, `block_schedule_loaded`,
  `block_start`, planned trial events, and `block_end`.
- [ ] No accepted emulated run contains `timing_anchor_fallback` unless the
  scenario intentionally tests degraded timing.
- [ ] Scheduled markers use `dac_time_sample_exact`; fallback timestamp modes
  are reported as failures for normal runs.
- [ ] Event counts match manifest composition exactly: `trial_start`,
  `looming_onset`, `tactile_onset`, `response_window_onset`, and `trial_end`.
- [ ] Final-boundary `trial_end` is present even when the event lands at block
  length.

### Emulated Response Model

- [ ] Use a ground-truth response plan keyed by `trial_uid`: hit, miss, early,
  late, double-click, out-of-target, cross-block, and instruction-click.
- [ ] Validate nominal hits at varied RTs across SOAs, blocks, parts, noise
  types, and respiratory phases.
- [ ] Boundary-test RT pairing: tactile +99 ms rejects, +100 ms accepts,
  +4.0 s accepts, and >4.0 s rejects.
- [ ] Verify noisy participant clicking is logged without corrupting analysis:
  all playback clicks remain in `events.csv`, but analysis and top-up use the
  first in-target click between tactile onset +100 ms and
  `min(tactile onset +4.0 s, next trial_start)`; double/random later clicks
  cannot overwrite the selected response.
- [ ] Verify a click at or after the next `trial_start` cannot bind to the
  previous trial.
- [ ] Verify one click can bind to only one tactile onset.
- [ ] Verify out-of-target and out-of-playback clicks are logged but excluded
  from analysis.
- [ ] Verify instruction-continuation clicks never appear as `mouse_click`
  responses.

### Response Marker Path

- [ ] Every in-playback accepted click creates one `mouse_click` and one linked
  `response_marker_start`.
- [ ] Every outside-playback click creates no response marker.
- [ ] `timing_qc.csv` links marker to mouse event ID and reports stable
  marker-minus-mouse delay.
- [ ] Test controller-level clicks, Qt `QTest` clicks, and at least one real
  OS-click backend (`win32`, `pynput`, or `pyautogui`) against the visible
  Focus Mode target.
- [ ] Confirm deferred LSL push preserves mouse-first, response-marker-next
  ordering.

### Instruction Module

- [ ] Exercise `before_experiment`, `before_each_block`, `after_each_block`,
  `between_conditions`, and `after_experiment`.
- [ ] Test `click`, `button`, and `delay` continuation modes.
- [ ] Missing or disabled instruction clips should log `instruction_missing` or
  skip cleanly without blocking the run.
- [ ] Stop during instruction audio should write outputs and mark the session
  interrupted.
- [ ] Double-clicking continuation should advance once, not create phantom
  responses.

### Top-Up Module

- [ ] A no-miss run logs `topup_not_needed` and creates no played top-up block.
- [ ] Controlled misses produce `topup_ledger.csv/json`, a draft manifest,
  `topup_block_ready`, approval, a played top-up block, and final analysis
  rescue rows.
- [ ] Miss reasons are covered: `response_deadline_expired`,
  `next_trial_started`, and `session_or_block_finished`.
- [ ] A multi-part run creates part-aware top-up blocks after each part
  boundary, not only at session end.
- [ ] Filler rows appear only when needed, have `Topup_Role=filler`, and have
  `Primary_Analysis_Included=false`.
- [ ] Rescue rows preserve `Source_Trial_UID`, source hashes, row labels, SOA,
  trial type, and part metadata.
- [ ] Top-up response clicks bind only to their top-up rescue/filler trial and
  cannot retroactively convert an older original miss into a hit across block
  or top-up context boundaries.
- [ ] Denied approval logs `topup_block_skipped` and leaves original misses
  unresolved.
- [ ] Top-up materialization failure logs `topup_block_materialize_failed` but
  still writes recoverable outputs.
- [ ] Misses inside top-up do not recurse into another top-up block.

### Data Outputs And Analysis

- [ ] Required outputs exist when enabled: `events.csv`, `events.xdf`,
  `lsl_markers.csv`, `lsl_markers.xdf`, `trigger_dictionary.json`, and
  `analysis_summary.txt`.
- [ ] Analysis CSVs are written: responses, analysis-ready trials, final trial
  outcomes, summary, curve points, sigmoid fits, model fits, model comparison,
  data-behavior-by-scope, and timing QC.
- [ ] `exploratory_quality_summary.json` is written when analysis CSVs are
  enabled and uses only exploratory labels (`Expected pattern`,
  `Mixed / ambiguous`, `Unusual pattern`, `Insufficient evidence`,
  `Technical caveat`) rather than pass/fail recording verdicts.
- [ ] The post-run `PPS Instant Analysis` dialog opens on `Data Behavior`,
  exposes Model Fits, Responses, Timing Evidence, Top-Up, and Artifacts views,
  and makes clear that the signals are operator feedback, not scientific
  conclusions or participant-readiness certification.
- [ ] Visual screenshot validation confirms plotted parameters are inspectable:
  SOA/distance x positions, metric axis, observed means, uncertainty band,
  sigmoid boundary marker, all-model overlay, raw/excluded/top-up point toggles,
  and low-N markers.
- [ ] Ground-truth planned hit/miss labels match `analysis_ready_trials.csv`.
- [ ] Top-up final outcomes replace only originally missed trials and never
  replace original hits.
- [ ] `primary_analysis_included=false` rows are excluded from final primary
  analysis.
- [ ] RT distributions in analysis match planned emulated delays within the
  expected UI/backend tolerance: strict maximum tolerance for deterministic
  controller/QTest backends, and strict p95 plus bounded maximum tolerance for
  visible OS-click backends.

### LSL And Trigger Codes

- [ ] Rich `PPSMarkersV2` and numeric `PPSTriggerCodes` receive matching event
  IDs and trigger codes when LSL is enabled.
- [ ] `trigger_dictionary.json` includes reserved control codes and
  deterministic trial trigger keys.
- [ ] Dynamic top-up trigger codes are written at session end.
- [ ] Capture-off combinations behave correctly: events-only, no LSL, no
  internal XDF, no trigger dictionary, no analysis CSVs.
- [ ] LSL unavailable path logs clear status and does not prevent local run
  completion.

### Operator Controls And Failure Modes

- [ ] Run `run_focus_runner_layout_validation.py --offscreen` and verify every
  standard screen scenario passes nonblank screenshots, embedded
  `layout_validation_failures()`, text visibility, splitter geometry, and
  keyboard shortcut-map checks.
- [ ] Confirm the `Experiment Control` panel starts at or above the adaptive
  profile height, spans the full lower workspace, and keeps the block order,
  top-up draft, tactile timeline, progress, and event labels visible without
  clipping or overlap.
- [ ] Confirm constrained screens switch operator details to tabs, ordinary and
  wide screens keep resizable splitters, and all panel handles remain large
  enough to drag.
- [ ] Exercise keyboard controls for automation and operator fallback: Space,
  Return, and Enter for start/continue; Ctrl+P for pause/resume; Ctrl+Shift+S
  for stop; Alt+1/Alt+2 for part selection; Ctrl+T for top-up preview; and
  Ctrl+W for closing after a stopped/completed run.
- [ ] Pause/resume logs `operator_pause` and `operator_resume` and does not
  corrupt later analysis.
- [ ] Stop mid-block logs `operator_stop`, `session_end interrupted=true`,
  writes partial outputs, and does not claim completion.
- [ ] Crash/error injection logs `session_error` and still writes recoverable
  logs where possible.
- [ ] Backup recording disabled, unavailable, start, and end paths all log the
  correct recording events.
- [ ] Long full-session realtime emulation runs at wall-clock duration, not
  fast-forward, when realtime mode is requested.

## Suggested Scenario Matrix

Run these as separate validation scenarios and write a machine-readable report
for each scenario:

- Full Study 5 packaged realtime emulation with randomized hits and misses.
  Finish this scenario by running
  `run_full_realtime_participant_emulation.py --audio-mode hardware --strict-study5-readiness`.
  This keeps standard capture enabled, captures a Focus Mode screenshot, writes
  compatibility launch/preparation reports, and invokes the strict Study 5
  readiness audit over the generated validation folder.
- Focus Mode adaptive layout and keyboard-control validation across the current
  PC available screen plus compact, laptop, desktop, and wide scenarios. The
  canonical gate is `run_focus_runner_layout_validation.py --offscreen`.
- One-block actual-condition emulation with real audio hardware and OS-click
  responses. This may pass `audit_protocol11_study5_readiness.py` as scoped
  local-recorder/XDF evidence, but it does not satisfy the final full-session
  gate.
- Boundary-response synthetic run with deterministic early, late, double, and
  out-of-target clicks. The canonical fast software gate is
  `run_protocol11_controlled_response_matrix.py`.
- Top-up adversarial run across two parts with approval accepted, denied, and
  failed.
- Capture-options matrix with LSL, XDF, trigger, and analysis toggles.
  `run_protocol11_capture_options_matrix.py` is the canonical fast local
  output-policy gate; it does not replace realtime Study 5 hardware/XDF/local
  recorder validation.
- Fault-injection matrix for missing assets, bad hashes, missing LSL, stopped
  run, and instruction errors.
- Generality run on at least one published non-Study-5 profile.

## Acceptance Standard

An accepted Protocol 11 report should include:

- the runner launch path and executable/build identity;
- the profile, participant ID, session manifest, and output root;
- the emulated response plan keyed by `trial_uid`;
- event-count and timestamp-quality audits for every played block;
- stimulus-assembly audits for every assembled block WAV;
- top-up ledger and final-outcome reconciliation when top-up is enabled;
- capture-option settings and resulting output file inventory;
- explicit pass/fail status for each checklist section;
- the Focus Mode layout validation report, including `Experiment Control`
  height/placement, adaptive splitters/tabs, nonblank screenshots, text
  visibility, and keyboard shortcut-map checks;
- the `audit_protocol11_study5_readiness.py` output for Study 5 runs, including
  XDF loadability, local audio-evidence WAV/sidecar checks, response-marker
  pulse recovery, screenshot validation, analysis RT agreement, and whether the
  artifact is truly full Study 5 realtime evidence;
- a short evidence-boundary note separating emulated software proof from
  physical timing, mechanical onset, and participant-facing scientific claims.
