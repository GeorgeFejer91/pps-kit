# Protocol 07: One-Block Actual Experimental Condition Validation

## Purpose

Validate the next-phase evidence standard: every formal runner/latency/data
collection test is performed on exactly one prepared experimental block under
actual experiment conditions.

Dummy pulse runs and fake-engine runner runs remain useful development
preflights. They are not accepted as next-phase experimental evidence.

This protocol is the default for the next phases of testing. Do not advance a
new formal claim about runner output, inter-channel latency, LSL/XDF capture,
response timing, or physical loopback reliability unless it has been checked on
one actual prepared block.

## Scope

An accepted actual-condition run must use:

- a Segment 5/6 prepared participant block
- one block only
- the real runner output folder for that block
- the real block CSV and block WAV generated from the prepared study
- `events.csv`
- `events.xdf` when XDF capture is enabled
- `lsl_markers.csv` and `trigger_dictionary.json` when LSL capture is enabled
- `*_analysis_ready_trials.csv`
- optional local audio evidence WAV plus direct loopback or response-marker
  loopback evidence when making physical timing claims

The validator is intentionally offline. It does not play audio, start LSL,
click the GUI, or touch the Komplete Audio 6.

The optional runner harness is not a product entry point. It exists only to
repeat this internal validation with lab safety controls: one actual block,
Komplete ASIO, conservative digital gain, full-duplex direct loopback capture,
and deterministic simulated clicks after tactile onsets.

## Procedure

1. Prepare the real study through the dashboard up to Segment 6.
2. Open the native runner from the Segment 6 manifest.
3. Use a non-participant validation ID.
4. Select exactly one block.
5. Enable the recording options needed for the question:
   - local event CSV
   - internal XDF
   - LSL marker mirror
   - trigger dictionary
   - analysis CSVs
   - local audio evidence WAV when the data-safety recording layer is under audit
   - direct physical loopback when physical timing is under audit
6. Run only that one block under the same audio route and stimulus settings
   intended for the experiment.
7. If response timing is being validated, inject jittered validation clicks
   after tactile onsets during the block.
8. If physical timing is being validated, capture direct electrical loopback
   or response-marker loopback for the same block.
9. Audit the resulting session folder:

```powershell
python .\For-AI/engineering/validation\scripts\validate_one_block_actual_condition_run.py `
  --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
```

If loopback evidence is required for the claim:

```powershell
python .\For-AI/engineering/validation\scripts\validate_one_block_actual_condition_run.py `
  --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS `
  --require-loopback-report
```

For the current lab setup, the repeatable hardware run can be launched with:

```powershell
python .\For-AI/engineering/validation\scripts\run_one_block_actual_condition_validation.py `
  --run-setup-manifest local_data\dashboard_projects\0_study_project_registry\profile_pfeiffer_2018_lateral_perihead_left_to_right\6_experiment_run_setup\experiment_run_setup_manifest.json `
  --device 31 `
  --audio-gain 0.005 `
  --tactile-gain 0.05
```

Then compare the actual block source WAV against its direct capture:

```powershell
python .\For-AI/engineering/validation\scripts\compare_actual_block_loopback.py `
  --session-dir artifacts\validation_runs\one_block_actual_condition_current\sessions\P001_YYYYMMDD_HHMMSS
```

## Acceptance Criteria

- The audited session is exactly one block.
- The session uses `participant_block_wavs` from a prepared Segment 5/6 source.
- The source does not look like a dummy pulse fixture or fake-engine validation
  fixture.
- The block WAV is three-channel.
- Local event IDs are unique.
- `trial_start`, `looming_onset`, `tactile_onset`,
  `response_window_onset`, and `trial_end` counts match the block trial count.
- Scheduled trial events are `dac_time_sample_exact`; no timing fallback is
  present.
- `*_analysis_ready_trials.csv` exists and has one row per tactile onset.
- `events.xdf` is loadable when required.
- `lsl_markers.csv` and `trigger_dictionary.json` exist when required.
- Mouse-click and response-marker records are complete when response timing is
  part of the run.
- Physical loopback claims are made only when a matching loopback report passes.
- Direct capture used for physical timing is unclipped.
- Actual block loopback comparison reports per-channel latency mean +/- SD and
  paired inter-channel skew mean +/- SD for the usable correlated trial
  segments.

## Interpretation

Use this protocol as the gate for next-phase evidence. Earlier dummy/fake
validation can explain why the pipeline is safe to run, but the formal
latency/reliability numbers for the experiment runner should come from
actual-condition one-block sessions.
