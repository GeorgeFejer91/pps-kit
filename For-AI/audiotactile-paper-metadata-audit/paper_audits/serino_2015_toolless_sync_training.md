# Serino/Canzoneri 2015 toolless sync training

- Record ID: `serino_2015_toolless_sync_training`
- DOI: `10.3389/fnbeh.2015.00004`
- DOI URL: https://doi.org/10.3389/fnbeh.2015.00004
- Coverage category: `covered_runnable_profile`
- Task family: bimodal IN/OUT target trials plus auditory-only catch trials
- Source route used for this pass: Frontiers publisher HTML, after Consensus MCP returned OAuth authorization required
- Manual review: `For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_toolless_sync_training.json`
- Validation script: `validation_protocols/scripts/run_serino_2015_toolless_known_parameter_profile_validation.py`
- Validation report: `artifacts/validation_runs/current_goal_serino_2015_toolless_known_parameter_20260715/serino_2015_toolless_known_parameter_validation_report.json`

## Extracted Runnable Contract

- 3000 ms pink-noise `IN` and `OUT` sounds.
- Two hidden loudspeakers: near about 5 cm from the participant's right hand, far about 100 cm from the near loudspeaker.
- Right-hand electrical tactile target via Digitimer DS7A and Neuroline/Ambu electrodes.
- Vocal response to tactile targets, with task-irrelevant sound ignored; auditory-only catches require response withholding.
- T1-T5 tactile delays: 300, 800, 1500, 2200, and 2700 ms from sound onset.
- One audio-tactile interaction block per PPS assessment session.
- The paper reports tactile stimulation in 77% of trials but does not print the exact catch count. The runnable profile uses the inherited Canzoneri-family 80 target rows and 24 catches because `80 / 104 = 76.9%`.

## Outcome Boundary

Expected scientific outcome: synchronous pairing of tactile hand stimulation with far auditory stimulation extends hand PPS without tool use, while asynchronous pairing does not. The validator checks the runnable measurement-block contract only. It does not execute the training intervention, reproduce original gain files, validate physical DS7A current/voice-key latency, collect participant behavior, or replicate the PPS effect.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `reported` | 3000 ms pink-noise samples | Frontiers HTML, Materials and procedures |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `reported` | IN far-to-near, OUT near-to-far | Frontiers HTML, Measuring PPS representation and Figure 6 caption |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `reported` | two hidden near/far loudspeakers | Frontiers HTML, Measuring PPS representation |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `reported` | audio-tactile target rows plus auditory-only catches | Frontiers HTML, Measuring PPS representation |
| `segment_2_sequence_and_intermixing` | `response_rule` | `reported` | vocal response to tactile target; withhold on catches | Frontiers HTML, Measuring PPS representation |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `reported` | DS7A electrical stimulation to right hand | Frontiers HTML, Measuring PPS representation |
| `segment_3_tactile_soa_baseline` | `soa_table` | `reported` | 300/800/1500/2200/2700 ms | Frontiers HTML, Figure 6 caption |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `reported_absent` | none for the measurement block | Frontiers HTML, Design |
| `segment_4_counts` | `target_count` | `protocol_lineage_derived` | 80 target rows | Frontiers article cites the Canzoneri-family task; toolkit profile preserves the 8 x 5 x 2 structure |
| `segment_4_counts` | `catch_count` | `derived` | 24 auditory-only catches | 77% target rate plus 80 target rows |
| `segment_4_counts` | `block_count` | `reported` | 1 assessment block | Frontiers HTML, Design |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
