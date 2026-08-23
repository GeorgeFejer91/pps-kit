# Protocol 06: End To End Stress Matrix

## Purpose

Run repeated deterministic sessions to estimate reliability across GUI settings,
audio routing, event logging, LSL, emulated responses, and physical loopback.
For next-phase evidence, each matrix cell is run as exactly one actual prepared
experimental block. Dummy/fake-engine runs can still be used as preflight
checks, but they are not counted as accepted experimental-condition evidence.

## Matrix

At minimum, run:

| Set | GUI/stimulus condition | Session density | Repeats |
| --- | --- | --- | ---: |
| A | Study 5 preload default | short deterministic | 5 |
| B | Custom single source | short deterministic | 5 |
| C | Multiple looming sources | medium | 5 |
| D | Dense SOA/event schedule | dense | 5 |
| E | Same as A after app restart | short deterministic | 3 |

Keep every run under a unique validation run folder and use non-participant IDs.

## Procedure

For each row in the matrix:

1. Run protocol 01 for GUI-to-artifact traceability.
2. Run protocol 02 before participant-style playback.
3. Optionally run the one-block realtime runner stress as a software preflight:
   `python .\For-AI/engineering/validation\scripts\run_one_block_trial_runner_realtime_stress.py --output-dir artifacts\validation_runs\one_block_trial_runner_realtime_current`
4. Run one prepared native session block under actual experiment conditions.
5. Run protocol 04 if LSL is installed.
6. Run protocol 05 if response timing is under audit.
7. Run protocol 07:
   `python .\For-AI/engineering/validation\scripts\validate_one_block_actual_condition_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS`
8. Run `summarize_validation_run.py`.
9. Copy the output into an acceptance report.

## Acceptance Criteria

- GUI-to-artifact traceability passes for every condition.
- Electrical loopback passes before session timing claims are made.
- Every run has complete local event logs.
- No official run uses `timing_anchor_fallback`.
- Each accepted run is exactly one actual prepared experimental block.
- One-block realtime runner stress writes analysis-ready trial rows, loadable
  `events.xdf`, `lsl_markers.csv`, and a trigger dictionary when used as a
  preflight.
- One-block actual-condition validation passes for the session folder.
- LSL probe receives all expected actual markers when enabled.
- Mouse click to response-marker links are complete and stable.
- Physical loopback session validation passes when recordings are available.
- Limitations are explicit, especially Woojer mechanical onset as not measured.

## Latency Budget Reporting

Report latency components separately:

- expected sample schedule
- callback/log timestamp behavior
- LSL probe arrival behavior
- electrical output-to-input latency
- response marker minus mouse click delay
- physical loopback residual timing
- not measured quantities
