# Missed-Trial Top-Up Stress Protocol

## Goal

Validate that opt-in missed-trial top-up mode works as a complete runner workflow:

- standard blocks play first;
- deliberately missed tactile trials are captured by the live ledger;
- one shortened top-up block is synthesized from existing trial WAVs;
- row-structure filler trials are inserted only when needed;
- the top-up block plays automatically when missed-trial top-up was enabled during setup;
- final analysis replaces original missed outcomes with top-up rescue outcomes.

## Scope

This is an internal software stress test. It uses a realtime fake audio engine and does not touch the Komplete interface, electrical loopback, or Woojer mechanics. It validates runner control flow, event logging, ledger persistence, top-up block synthesis, and immediate analysis tables.

## Command

```powershell
python .\validation_protocols\scripts\run_topup_missed_trial_stress.py `
  --output-dir artifacts\validation_runs\topup_missed_trial_stress_current `
  --block-count 2 `
  --trials-per-block 6 `
  --trial-duration-s 0.65
```

## Acceptance Criteria

- Every planned deliberate miss appears in `topup_ledger.csv`.
- Exactly one top-up block is played, and it is played after all standard blocks.
- `topup_block_manifest.csv/json` contains one `rescue` row per missed original trial.
- `filler` rows appear only to preserve row order and are excluded from primary analysis.
- `final_trial_outcomes.csv` contains the original planned trial pool, with rescued misses marked as `final_outcome_source = topup_rescue`.
- `analysis_ready_trials.csv` has the same planned-trial count as the original tactile pool.
- The run writes normal session artifacts: `events.csv`, `events.xdf`, `lsl_markers.csv`, `trigger_dictionary.json`, timing QC, model fits, and analysis summary according to capture options.

## Evidence Boundary

Passing this protocol proves the software top-up workflow under emulated participant behavior. It does not prove hardware latency, direct electrical output timing, LSL external-recorder behavior, or Woojer vibration onset.
