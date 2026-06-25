# Protocol 10: Real-Participant, Real-Experimenter Full-Session Stress Test

## Purpose

Everything validated so far has used **simulated clicks, fake or single-block
audio, or automated mouse emulation** (Protocols 03-09; the
`full_realtime_participant_emulation` artifact). None of it proves the runner
delivers a correct experiment when an **actual human participant perceives the
stimuli and responds**, and an **actual experimenter operates the runner**
through a full, multi-block, two-part Study 5 session.

This protocol is the acceptance gate for that claim. It stress-tests every
function `PPSExperimentRunner.exe` / Focus Mode / `SessionRunnerController`
performs, end to end, with real people and real hardware (Komplete Audio 6 MK2
ASIO + Sennheiser headphones + Woojer tactile), and it audits the resulting data
for scientific usability — not just file presence.

## How To Use This Checklist

- Run it on the **default Study 5 two-part profile** first, then repeat the
  hardware-independent sections for at least one published profile (e.g.
  `pfeiffer_2018_lateral_perihead_left_to_right`) to confirm generality.
- Each item is `[ ]` = not run, `[x]` = pass, `[!]` = fail/blocked (log a
  defect). A criterion is **passed only when the stated threshold is met and the
  named output file/event actually contains the expected value** — presence is
  not pass.
- Use a **non-clinical pilot participant** plus a **separate experimenter** for
  the first full pass. The participant must not be the experimenter.
- Record every run's `session_id`, `local_data/sessions/<id>/` path, build hash
  of the exe, audio device index, and gains used.
- Keep at least one full run with the **fail-safe local audio evidence WAV
  enabled** so cross-layer reconciliation (Section N) is possible.

Legend for thresholds referenced below (Study 5 timing contract):
trial = 8.000 s; instruction segment = 4.000 s; looming segment = 4.000 s;
tactile cue = 100 ms; SOAs = 0/300/800/1500/2200/2700 ms; response window
min RT = 0.1 s, max RT = 4.0 s; channels = ch0 left / ch1 right / ch2 tactile;
ASIO 3-channel, requested latency 0.010, blocksize 256.

---

## A. Pre-Flight: Environment, Hardware & Apparatus Readiness

- [ ] **A1. Validated audio route present.** `pps-audio-stress` / Stress_Audio
  passes 3-channel silent playback on the Komplete Audio **ASIO** endpoint
  (not the stereo Output 1/2 + 3/4 split). Confirm the runner auto-selects
  "Komplete Audio ASIO Driver", not a WDM/ASIO4ALL fallback.
- [ ] **A2. Qt runtime preflight passes.** Build preflight finds
  `qwindows.dll` in `_internal\PySide6\plugins\platforms\`; the exe opens Focus
  Mode without a missing-plugin error. PySide6 is on the pinned 6.7.x line.
- [ ] **A3. Persistent single-stream stability.** A 60+ s continuous callback
  stress at the production settings (3 ch / 0.010 / 256) shows no buffer
  underruns and stable ~16-17 ms actual latency. Confirm the runner uses **one
  persistent ASIO stream** for block + instruction + click feedback (concurrent
  streams are known to fail on this device).
- [ ] **A4. Physical channel mapping verified by ear and by loopback.** Left
  WAV channel → left Sennheiser, right → right Sennheiser, ch2 → Woojer tactile.
  Confirm no L/R swap and no tactile bleed into the headphones.
- [ ] **A5. Electrical loopback baseline current.** A direct 3-channel loopback
  recovers all channels with the known baseline (~33.6 ms output→input,
  L/R skew ~0.02 ms, tactile/audio skew ~0.01 ms, 0 ms residual jitter).
  Re-measure if cabling/driver changed.
- [ ] **A6. Woojer mechanical-onset gap acknowledged.** The Woojer's *mechanical*
  vibration latency is **not** in the electrical loopback. Decide and document
  whether this run measures it (accelerometer/mic on the strap) or explicitly
  defers it. Do not silently claim tactile timing the loop never measured.
- [ ] **A7. Headphone/tactile levels set on a person, safely.** Looming peak SPL
  and Woojer intensity are set with the actual participant to comfortable,
  non-startling, supra-threshold levels **before** logging real trials; record
  the gains. Production gains differ from the conservative validation gains
  (`audio_gain≈0.0005`, `tactile_gain≈0.02`) — do not run a participant at
  inaudible validation gains.
- [ ] **A8. Tactile detectable but not trivially salient.** Confirm the 100 ms
  ch2 cue at the chosen gain is reliably *felt* across the SOA range yet still
  yields genuine misses (otherwise top-up and the miss ledger can't be tested).
- [ ] **A9. Room / EEG / LSL recorder ready (if used).** LabRecorder sees both
  `PPSMarkersV2` and `PPSTriggerCodes`; EEG trigger box reads numeric codes.
- [ ] **A10. Workspace path length safe.** Session/manifest paths stay under the
  legacy 260-char Windows boundary (long Segment 6 paths have caused false
  missing-file checks).

## B. Launch, Session Resolution & Participant Selection

- [ ] **B1. Dashboard handoff launch.** Segment 6 "Save Design and Start
  Experiment Runner" materializes the participant session and opens Focus Mode
  via `PPSExperimentRunner.exe --session-manifest ...`; no capture flags are
  passed (runtime choices belong to Focus Mode).
- [ ] **B2. Standalone profile launch.** Launcher `Study/profile preset` +
  `Run Selected Profile` (or `--profile <id> --participant-id <id>`) prepares the
  session and opens Focus Mode for the same profile.
- [ ] **B3. Resume order honored.** With no argument, the exe auto-opens the last
  **launchable** session ready-to-start; `--launcher` forces the picker. Verify
  precedence: explicit `--session-manifest` → valid last session → valid last run
  setup → newest prepared Segment 6 → manual picker.
- [ ] **B4. Resume ledger integrity.** Only `run_setup_prepared`,
  `session_prepared`, `runner_launched` update `last_experiment.v1.json`; edits /
  test work in `experiment_activity_log.jsonl` do **not** clobber a valid resume
  pointer.
- [ ] **B5. Participant dropdown correctness.** Participant control is a
  **dropdown** (not free text), sourced from the Segment 6 list (P001-P050 for
  Study 5). Each row shows generated/asset state; rows with existing data show a
  `[collected]` marker; default selection prefers first generated,
  not-yet-collected participant.
- [ ] **B6. Out-of-plan IDs rejected.** An ID not in the prepared block-order
  plan fails *before* session materialization with a clear message (does not
  silently invent a session).
- [ ] **B7. Background prep is responsive.** Profile/participant prep runs in a
  background worker with live status phases (inventory → segment checks → WAV
  load → block assembly/cache → manifest write → opening Focus Mode), progress,
  detail text, and a working Cancel. A 20-30 s WAV build never looks frozen.
- [ ] **B8. Mid-run participant switch.** Selecting a different participant
  **before playback** re-materializes/reuses that package and refreshes labels,
  block plan, idle timeline, and output summary; `participant_code` is derived
  from the package, not operator text.

## C. Stimulus Assembly & Participant Package Materialization

*(the "stimulus assembly" level the runner must get right before a single trial plays)*

- [ ] **C1. Authoritative order respected.** The session uses Segment 6 as the
  authoritative participant/phase/block order, filtered to the selected
  participant, resolving the accepted Segment 5 `block_XX_final.csv` files.
- [ ] **C2. `execution_mode = participant_block_wavs`.** One continuous WAV is
  written per ordered participant block under
  `local_data/sessions/<id>/blocks/`; the session is not a dummy/fake fixture.
- [ ] **C3. Three-channel assembly.** Every assembled block WAV is 3-channel with
  ch0/1 = binaural L/R and ch2 = tactile; mono ingredients were centered to L+R
  and never collapsed the stereo looming pair to mono.
- [ ] **C4. Tactile inserted only at assembly.** Tactile cue appears in ch2 at the
  scheduled SOA per trial; Segment 1/2 auditory sources remained tactile-free
  upstream. Catch trials carry **no** ch2 cue; baseline trials carry ch2 cue with
  (per strategy) silent or full L/R.
- [ ] **C5. Sample-accurate trial geometry.** Block CSV sample-position columns
  (`Trial_Start_Sample`, `Looming_Onset_Sample`, `Tactile_Onset_Sample`,
  `Response_Window_Onset_Sample`, `Trial_End_Sample`) match the 8.000 s grid and
  the requested SOA at the file's sample rate (verify a few rows by hand:
  tactile_onset_sample ≈ trial_start + (4.000 s + SOA) × Fs).
- [ ] **C6. Row-order invariant preserved.** Within every block the Segment 2/3
  row sequence cycles correctly (Study 5: inhale, exhale, inhale, exhale …).
  Randomization changed *which* concrete trial fills each row slot, never the row
  order.
- [ ] **C7. Audible content matches labels.** Spot-listen assembled blocks:
  inhale rows carry inhale instruction, looming actually looms (110→10 cm sweep),
  the noise type (pink/blue/white/brown) matches the CSV `Noise_Type`.
- [ ] **C8. Cache correctness.** A cache hit (hardlink or copy fallback) produces
  a block **bit-identical** to a fresh assembly for the same fingerprint
  (Segment 5 CSV + run setup + source hashes + setup signature + cache version);
  a changed upstream input forces a cache miss.
- [ ] **C9. Prewarm safety.** After Focus Mode opens, only the *next* Segment 6
  participant is prewarmed into `prepared_session_queue.v1.json`; prewarm never
  auto-starts playback, never blocks the UI/audio callback, and defers heavy
  assembly once playback is active. A stale fingerprint invalidates the queued
  entry.
- [ ] **C10. No writes under `_internal`.** Live sessions/dashboard state are
  written under `writable_root()` (`local_data/...`), never inside the
  PyInstaller `_internal` resource tree.

## D. Participant Metadata, Consent & Privacy

- [ ] **D1. Demographics captured.** Focus Mode collects code, name, age,
  handedness, gender before playback; values land in `session_metadata.json`.
- [ ] **D2. Name-sharing opt-in is OFF by default and authoritative.** With the
  name checkbox **unchecked**, the real name appears only in **local**
  `session_metadata.json`; it is **absent** from `session_start`, LSL stream
  descriptors, `lsl_markers.*`, and `events.csv` (a pseudonym is used). Grep the
  shared outputs for the entered name and confirm zero hits.
- [ ] **D3. Opt-in emits name only when checked.** With the box checked, the name
  appears in `session_start`/LSL metadata as designed — and the participant
  consented to that.
- [ ] **D4. Pseudonym stability.** The generated pseudonymous `participant_code`
  is consistent across `events.csv`, LSL, and analysis CSVs for the session.
- [ ] **D5. Capture options recorded.** `session_start.capture_options` and
  `session_metadata.json` record exactly which layers were enabled (events CSV,
  internal XDF, LSL mirror, trigger dictionary, analysis CSVs, audio evidence
  WAV, top-up).

## E. Run-Level Instruction Audio Module

- [ ] **E1. All five slots fire in order.** `before_experiment` (Study 5
  `General_Instructions.wav` ~85.7 s), `before_each_block` (~8.4 s),
  `after_each_block` (~8.8 s), `between_conditions` (~10.1 s),
  `after_experiment` (~7.0 s) play at the correct boundaries.
- [ ] **E2. Instruction events logged.** Each plays `instruction_start` →
  `instruction_end`; continuation produces `instruction_continue` with its
  source (operator/click/timed).
- [ ] **E3. Continuation clicks are NOT responses.** A click used only to advance
  an instruction never appears as a trial `mouse_click` and is **never** paired
  to a tactile onset in `analysis_ready_trials.csv`. Verify by clicking to
  advance and confirming no phantom hit.
- [ ] **E4. Continuation modes work.** Test click-target, timed-delay, and
  runner-button continuation; each advances exactly once and cannot double-fire.
- [ ] **E5. Optional/missing slots never block.** A disabled or missing clip logs
  `instruction_missing` / `instruction_error`, is skipped with a warning, and the
  run continues; the final runner action is never disabled by an empty
  instruction slot.
- [ ] **E6. Between-condition placement.** `between_conditions` fires only at the
  pre→post boundary (not between same-condition blocks); `after_each_block` only
  fires when another block in the same condition follows.

## F. Block Playback & Timing Authority

- [ ] **F1. `audio_sample_zero` anchors every block.** Each block logs
  `audio_sample_zero` from the audio callback; no block falls back to
  `timing_anchor_fallback` / `block_anchor_fallback`. If any block fell back,
  treat its timing as degraded and record it.
- [ ] **F2. Planned-event completeness.** Per block, counts of `trial_start`,
  `looming_onset` (audio-tactile + catch), `tactile_onset` (audio-tactile +
  baseline), `response_window_onset`, and `trial_end` match the block's trial
  composition exactly.
- [ ] **F3. `trial_end` at exact block length.** The final `trial_end` lands at
  the sample-exact block duration (final-boundary event present).
- [ ] **F4. Timestamp quality.** Scheduled trial markers are
  `dac_time_sample_exact` (sample-anchored via `audio_sample_zero + n/Fs`), not
  per-buffer PortAudio timing. Verify late-block markers show no drift.
- [ ] **F5. SOA fidelity (real audio).** From the audio-evidence WAV or loopback,
  measured tactile-onset minus looming-onset matches each requested SOA within a
  tight tolerance (e.g. < 1-2 ms after removing the constant route latency).
- [ ] **F6. Inter-channel skew within spec.** Left/right and tactile/audio skew
  stay near the A5 baseline across the block (no growing divergence).
- [ ] **F7. No clipping / dropped buffers.** Audio-evidence WAV (if enabled)
  reports zero dropped buffers and no clipping at production gains.
- [ ] **F8. Pause/Resume/Stop integrity.** Pausing halts playback and suppresses
  cursor recenter; resume continues without corrupting the sample schedule;
  stop ends cleanly, writes outputs, and marks the session interrupted.

## G. Response Capture & Cursor Recenter

- [ ] **G1. Real clicks logged.** Participant clicks in the CLICK target log
  `mouse_click` with `in_target`, `during_playback`, and x/y; out-of-target or
  out-of-playback clicks are flagged accordingly and excluded from pairing.
- [ ] **G2. Response-marker ordering.** Runner order holds: log mouse click
  locally (gets event id) → trigger ch2 response marker → push mouse marker to
  LSL. Marker-minus-mouse delay ≈ the intended 8 ms (mean ~8.1 ms, SD < 0.1 ms
  in prior stress).
- [ ] **G3. RT window correctness.** A click is credited only when
  onset + 0.1 s ≤ click ≤ min(onset + 4.0 s, next trial_start). Verify a too-fast
  (<100 ms) click and a too-late (>3 s) click are **not** credited.
- [ ] **G4. One click → one trial.** No click is credited to two tactile onsets;
  cross-block / cross-part clicks never bind to an earlier trial
  (`_same_trial_context`).
- [ ] **G5. DPI hit-test correct.** On the actual lab display scaling, the
  CLICK-target hit test matches the visible target (historic Windows DPI bug);
  participant clicks at the visible center register as `in_target`.
- [ ] **G6. Cursor recenter behavior.** The pointer recenters on the CLICK target
  ~500 ms before each planned tactile onset; it **never auto-clicks**, ignores
  catch/audio-only trials, and is disabled during instruction waits, pause, and
  stop. Confirm it does not fight the participant's hand or generate clicks.
- [ ] **G7. Catch trials yield no tactile and no required response.** Catch trials
  log `looming_onset` but no `tactile_onset`; a click on a catch trial is not a
  "hit" against any tactile onset.

## H. Event & Data-Logging Integrity

- [ ] **H1. `events.csv` always-on and complete.** Present, monotonic
  `unix_time`/`monotonic_time`, **unique** `event_id`s, no gaps; payload JSON
  parses for every row.
- [ ] **H2. `events.xdf` loadable.** Loads with `pyxdf`; sample count equals the
  event count; first/last timestamps consistent with the session.
- [ ] **H3. Dual LSL streams mirrored from runtime.** `lsl_markers.csv` +
  `lsl_markers.xdf` contain both `PPSMarkersV2` (rich string) and
  `PPSTriggerCodes` (numeric) and are mirrored from the **same runtime marker
  records**, not reconstructed from planned CSVs.
- [ ] **H4. Trigger dictionary consistency.** `trigger_dictionary.json` maps every
  emitted event type/key to a stable numeric code; codes in `lsl_markers` all
  resolve in the dictionary; no collisions.
- [ ] **H5. Sample-anchored LSL timestamp error tiny.** Internal LSL timestamp
  error vs sample anchor stays negligible (prior p95 < 1e-6 ms).
- [ ] **H6. `session_metadata.json` complete.** Demographics (local), capture
  policy, run timestamp, experiment/project/template fields, manifest
  paths+hashes, and design/run-setup snapshots all present.
- [ ] **H7. LSL-unavailable degrades gracefully.** If `pylsl`/LabRecorder is
  absent, the session still writes internal `events.xdf` + local marker mirrors,
  and `lsl_status` records unavailability instead of aborting the run.
- [ ] **H8. Audio-evidence sidecars.** If enabled, each
  `recordings/Block_XX_*_audio_evidence.wav` has its metadata sidecar and matches
  the played block.

## I. Top-Up Module (Missed-Tactile Recovery)

- [ ] **I1. Live miss ledger.** During playback `topup_ledger.csv/json` accrue
  one row per tactile trial with status pending → hit/`missed_needs_topup`;
  `topup_draft` progress updates as response windows pass.
- [ ] **I2. Miss reasons correct.** Misses are labeled `response_deadline_expired`
  / `next_trial_started` / `session_or_block_finished` as appropriate; a real
  participant's genuine misses are captured (engineer ≥ a few real misses to
  exercise this — see A8).
- [ ] **I3. Part-aware finalization.** At each part boundary, open trials for that
  part finalize; misses from Part 1 do not leak into Part 2's top-up and vice
  versa.
- [ ] **I4. Checked setup auto-plays top-up.** When missed-trial top-up is
  submitted on, `topup_block_ready` proceeds to `topup_block_approved` and plays
  without an additional operator prompt. When it is submitted off, no top-up
  ledger/draft/block is produced.
- [ ] **I5. Rescue content fidelity.** The top-up block replays the **actual
  missed tactile trials** from that part with their original stimulus identity,
  preserving Segment 2/3 row order; `source_trial_uid` links each rescue to its
  original.
- [ ] **I6. Filler rows excluded from primary analysis.** Filler rows added only
  to preserve row structure carry `topup_role = filler` and
  `primary_analysis_included = false`; they never count as rescues.
- [ ] **I7. No recursive top-up.** Misses *within* a top-up block are not
  themselves topped up.
- [ ] **I8. Top-up outputs land in the session.** `blocks/*topup_missed_trials.wav`
  (per part: `..._partN_...`), part-specific
  `topup_block_manifest_partN.csv/json`, and `topup_ledger.csv/json` exist;
  `SessionRunResult.analysis_outputs` exposes `topup_block_wav_partN`.
- [ ] **I9. Top-up appears correctly in the timeline.** It shows as the final
  block within its part (part-local numbering), not as a spurious global block.
- [ ] **I10. Top-up disabled path.** With the checkbox off, no ledger/draft/block
  is produced and the run is unaffected.

## J. Analysis Outputs & Behavioral Data Quality

- [ ] **J1. `analysis_ready_trials.csv` — one row per tactile onset.** Row count
  equals total `tactile_onset` events; each row has condition/part/block/trial
  identity, `soa_ms`, `family`, `noise_type`, `respiratory_phase`, `hit`,
  `rt_ms`, `click_x/y`, `click_event_id`.
- [ ] **J2. `final_trial_outcomes.csv` reconciles top-up.** Columns
  `original_hit`, `rescued_in_topup`, `topup_trial_uid`, `topup_rt_ms`,
  `topup_hit`, final `hit`, `final_outcome_source`
  (original/topup_rescue/topup_rescue_orphan), `analysis_exclude_reason`.
  A trial missed originally and hit in top-up shows `rescued_in_topup = true` and
  final `hit = true`.
- [ ] **J3. RT plausibility (real human).** Hit `rt_ms` distribution is
  physiologically sensible (roughly ~200-900 ms mode, essentially none < 100 ms
  after the floor, tail < 3000 ms). Flag any pile-up at the 100 ms floor (anticip-
  ation) or 3000 ms ceiling (the participant may not understand the task).
- [ ] **J4. Hit rate sane by family.** Audio-tactile/baseline hit rate is high but
  not 100% (some genuine misses); catch trials generate essentially no spurious
  tactile "hits".
- [ ] **J5. PPS curve emerges.** Per-SOA hit/RT summaries and the model-fit CSVs
  (sigmoid vs linear vs log) produce a **monotonic, interpretable
  proximity/SOA effect** for a cooperative participant — the headline scientific
  signal the toolkit exists to capture. If the curve is flat/noise, investigate
  before accepting the run.
- [ ] **J6. Baseline subtraction correct.** Baseline means are computed and
  applied per condition/phase/SOA as designed; baseline trials are not mislabeled
  as audio-tactile.
- [ ] **J7. `timing_qc.csv` clean.** Per-event timing-quality summary shows
  expected counts and no unexpected fallbacks.
- [ ] **J8. `analysis_summary.txt` matches CSVs.** Reported total trials, detected
  responses, and hit rate equal what the CSVs contain.
- [ ] **J9. Condition labeling.** Two-part runs label `pre`/`post` internally but
  surface Condition 1/Condition 2; analysis CSVs preserve the internal phase for
  reproducibility.

## K. Multi-Part, Counterbalancing & Reproducibility

- [ ] **K1. Both parts run.** A two-part session plays Part 1 fully, transitions
  via `between_conditions`, runs Part 2, and can produce one top-up block per
  part.
- [ ] **K2. Counterbalanced block order.** Different participants receive
  different block orders per the Segment 6 permutation seed; the same participant
  is reproducible from the recorded seed.
- [ ] **K3. No-immediate-repeat ordering.** Within-block trial ordering respects
  the no-immediate-repeat default while preserving row structure.
- [ ] **K4. Seed/recipe recorded.** The permutation seed and all manifest hashes
  are written so the exact session can be regenerated.

## L. Run Control, Interruption & Recovery

- [ ] **L1. Graceful stop mid-block.** Operator stop writes partial
  `events.csv`/XDF/LSL/analysis, marks `interrupted = true`, and adds the
  "interrupted before all blocks completed" warning.
- [ ] **L2. Crash/kill safety.** Force-kill the exe mid-block; confirm
  `events.csv` (always-on safety copy) retains everything up to the kill and is
  still parseable; no half-written session blocks the next launch.
- [ ] **L3. Resume after interruption.** Relaunch resolves to the right resume
  target and does not silently overwrite a prepared setup.
- [ ] **L4. Audio device yanked.** Disconnect/disable the ASIO device mid-run;
  the runner surfaces a clear error (`session_error`) and still flushes outputs
  rather than hanging.
- [ ] **L5. Instruction-wait stop.** Stopping while awaiting an instruction
  continuation exits cleanly without crediting a response.

## M. Endurance & Full-Length Session

- [ ] **M1. Full Study 5 length completes.** A complete two-part run (all blocks
  + both top-ups, ~hour-scale; emulation wall time was ~3800 s) completes with
  `completed = true` and no memory/handle growth, audio glitch, or UI freeze.
- [ ] **M2. Wall time ≈ expected.** Process wall time ≈ summed played
  audio+instruction duration (small overhead only).
- [ ] **M3. No late-session timing drift.** Last-block markers are as
  sample-accurate as first-block markers (F4 holds at the end).
- [ ] **M4. Participant comfort sustained.** No fatigue/startle/discomfort that
  would invalidate late trials; break structure adequate.

## N. Cross-Layer Data Reconciliation (the real-participant proof)

*Run with audio-evidence WAV + (optional) external LSL/XDF + loopback enabled on
at least one real block.*

- [ ] **N1. Five layers agree.** For one real block, `compare_recording_layers.py`
  reconciles physical loopback WAV, local audio-evidence WAV, `events.csv`,
  internal `lsl_markers.csv/xdf`, and external LSL/XDF — counts and ordering
  match after removing the constant route offset.
- [ ] **N2. Physical-vs-digital latency stable.** Physical-minus-digital latency
  matches the A5 baseline (~33.5 ms, tight SD).
- [ ] **N3. Real response markers recovered.** Participant-driven ch2 response
  markers are recovered in the tactile-channel loopback with ~0 ms residual
  jitter after fitting the common offset.
- [ ] **N4. External XDF preserves both streams.** LabRecorder XDF contains
  `PPSMarkersV2` + `PPSTriggerCodes` and reconciles against the local mirrors
  (`run_labrecorder_lsl_xdf_stress.py` / `reconcile_lsl_with_local_events.py`).
- [ ] **N5. No event lost between layers.** Every `tactile_onset` and credited
  `mouse_click` in `events.csv` has a corresponding LSL marker and (where
  physically visible) a loopback pulse.

## O. Real-Participant Experiential & Task Validity

- [ ] **O1. Task is performable as instructed.** The participant understands and
  executes the breathing-phase + looming + click task from the recorded
  instructions alone (no experimenter ad-lib needed).
- [ ] **O2. Stimuli perceived as intended.** Post-run, participant confirms the
  looming sound was heard as approaching, tactile cues were felt, and L/R/spatial
  motion matched the design (sanity check against C7/A4).
- [ ] **O3. Responses reflect perception, not artifact.** Hits track felt tactile
  cues, not cursor recenter motion or audio onsets; spot-check a few trials
  against the participant's reported experience.
- [ ] **O4. Breathing phases align.** Inhale/exhale instruction clips line up with
  the intended respiratory phase rows; the participant could follow the pacing.
- [ ] **O5. Debrief captured.** Confusing moments, missed cues, discomfort, and
  any apparatus oddities are logged as qualitative defects for the next run.

## P. Experimenter Operability

- [ ] **P1. Operator can run it unaided.** A trained-but-non-developer
  experimenter completes setup → launch → participant entry → full run → locate
  outputs using only the runner UI and docs.
- [ ] **P2. Status is legible during run.** Header chips (Part, Block n/N, run
  state), live tactile timeline, cue/click counts, and next-cue countdown are
  visible and correct on the lab display.
- [ ] **P3. Controls reachable.** CLICK target, run controls, and top-up setup
  are mouse-reachable in taskbar-aware maximized mode (not clipped/off-screen);
  block-preview clicking never disturbs live playback/recenter.
- [ ] **P4. `Open Session Folder` works.** Operator can open the session output
  folder from the UI and find all expected files.
- [ ] **P5. Errors are actionable.** Any error message (audio route, missing
  asset, bad ID) tells the operator what to do, not just that something failed.

## Q. Edge Cases & Failure Injection

- [ ] **Q1. Zero misses.** A near-perfect participant → `topup_not_needed`,
  no top-up block, analysis still correct.
- [ ] **Q2. Many misses / row-imbalanced misses.** Heavy misses produce a valid
  top-up block with filler rows only where needed (mirror Protocol 08 scenarios
  with a real hand).
- [ ] **Q3. Double-click / rapid clicks.** Multiple clicks in one window credit at
  most one hit; extras are logged but not double-counted.
- [ ] **Q4. Click exactly at window edges.** Clicks at onset+0.1 s and at
  next-trial boundary behave per the inclusive/exclusive rules in G3.
- [ ] **Q5. Missing instruction asset at runtime.** Remove one enabled clip before
  launch → `instruction_missing`, run continues.
- [ ] **Q6. Catch-only / baseline-only stretches.** Blocks with runs of catch or
  baseline trials log correctly and don't desync the schedule.
- [ ] **Q7. Re-run same participant.** A second session for the same ID creates a
  new timestamped folder, never overwrites the first, and `[collected]` marking
  updates.

## R. Acceptance & Sign-Off

- [ ] **R1.** All Section H/I/J data-integrity items pass on the full Study 5
  two-part run (no `[!]`).
- [ ] **R2.** Section F/G/N timing items pass on ≥1 real block with loopback;
  Woojer mechanical-onset status (A6) explicitly documented.
- [ ] **R3.** Section J shows an interpretable PPS curve for ≥1 cooperative
  participant.
- [ ] **R4.** One published-profile run (e.g. Pfeiffer) passes the
  hardware-independent sections (B, C, E, F, H, J, K) to confirm generality.
- [ ] **R5.** Defects logged with session_id, layer, expected vs actual, and a
  repro path; blockers triaged before real data collection.
- [ ] **R6.** Final claim is scoped honestly: which timing layers were physically
  measured vs reconstructed, and what remains unmeasured.

### Run Record (fill per session)

| Field | Value |
|---|---|
| Date / experimenter / participant (pilot) | |
| Exe build hash / profile / parts | |
| Audio device index / audio gain / tactile gain | |
| session_id / session folder | |
| Capture layers enabled | |
| Blocks planned / completed / top-up blocks | |
| Total tactile onsets / hits / hit rate | |
| Mean hit RT (ms) / RT range | |
| Fallback-timing blocks (should be 0) | |
| PPS curve interpretable? (Y/N) | |
| Cross-layer reconciliation pass? (N1-N5) | |
| Defects (IDs) | |
| Accept / reject | |

---

### Coverage Map — what each section proves vs. prior evidence

| Section | Runner function | Prior evidence | Real-run gap closed |
|---|---|---|---|
| A | Audio route / apparatus | audio-stress, loopback baseline | levels set on a person; Woojer mechanical onset |
| B | Launch / resume / selection | UI mouse emulation | real operator, real choices |
| C | Stimulus assembly / cache | one-block actual condition | full multi-block assembly + cache + prewarm |
| D | Metadata / privacy | redaction unit checks | real name privacy end-to-end |
| E | Instruction module | Study 5 UI emulation | real continuation behavior, no phantom hits |
| F | Playback timing | recording-layer anchor | full-length, real audio, real SOAs |
| G | Response capture | simulated/emulated clicks | **real human clicks & perception** |
| H | Event/LSL logging | one-block, labrecorder stress | full-session integrity |
| I | Top-up | fake-audio topup stress | **real misses, checked setup auto-play** |
| J | Analysis / data quality | synthetic RT fixtures | **real behavioral PPS signal** |
| K | Counterbalance/parts | UI emulation | full two-part real run |
| L | Control/recovery | — | real interruption/crash/device-loss |
| M | Endurance | 3800 s emulation | **real participant full length** |
| N | Cross-layer reconcile | anchor block | real-response multi-layer agreement |
| O | Task validity | — | **does the experiment measure PPS** |
| P | Operability | — | real experimenter usability |
| Q | Edge cases | topup scenarios | real-hand edge behavior |
