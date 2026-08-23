# Canzoneri et al. (2013b)

- Record ID: `canzoneri_2013_amputation_prosthesis`
- DOI: `10.1038/srep02844`
- DOI URL: https://doi.org/10.1038/srep02844
- Coverage category: `covered_runnable_profile`
- Task family: Canzoneri-style dynamic PPS task
- PDF status: `downloaded`
- Supplement status: `not_found_or_not_required_for_core_profile`
- Extraction status: `manual_review_completed_open_access_pdf`
- Metadata confidence: `0.86` (`high_confidence_extraction_with_source_count_caveat`)
- Manual review: `For-AI/research/literature/audiotactile-paper-metadata-audit/manual_reviews/canzoneri_2013_amputation_prosthesis.json`
- Known-parameter validation: `artifacts/validation_runs/current_goal_canzoneri_2013_amputation_known_parameter_20260715/canzoneri_2013_amputation_known_parameter_validation_report.json`

## Source Review Result

- Open-access Nature Scientific Reports HTML and PDF were reviewed on 2026-07-15.
- Core audio-tactile parameters are now captured in the runnable profile: 3000 ms pink-noise IN/OUT sounds, 1000 ms pre/post silence, near/far loudspeaker layout separated by about 100 cm, T1-T5 tactile timings at 300/800/1500/2200/2700 ms, upper-arm electrical tactile target context, 76 auditory-only catch trials, and two blocks.
- Clinical limb/prosthesis state is retained as paper-level context. It does not alter the sound/tactile row mechanics needed for the runnable PPS task profile.

## Source Count Caveat

- The PDF Methods sentence reports 8 target stimuli for each temporal delay for IN and OUT sounds, which implies 80 tactile-target rows.
- The same sentence says this resulted in 76 tactile-target trials. No cell-level 76-row distribution was found.
- The toolkit profile preserves the coherent factorial target structure, 5 delays x 2 directions x 8 repetitions = 80 target rows, plus the explicitly reported 76 auditory-only catches. The literal 76-target wording remains a source inconsistency caveat, not a hidden normalization.

## Expected Outcome

- Healthy/control and healthy-limb rows show faster tactile RTs as perceived sound distance approaches the body.
- Amputated-limb testing without the prosthesis shifts PPS coding toward the stump and slows responses relative to healthy-limb conditions.
- Wearing the prosthesis speeds amputated-limb responses and restores/extends PPS coding toward the prosthetic hand.
- Experiment 3 supports the interpretation that sound position is coded relative to the stimulated limb boundary.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `reported` | Pink-noise dynamic auditory stimulus. | PDF p.7, Methods, Experiment 2 and 3 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `reported` | Near loudspeaker close to upper arm, far loudspeaker about 100 cm away; IN far-to-near, OUT near-to-far. | PDF p.7, Methods |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `reported` | 3000 ms sound plus 1000 ms pre/post silence. | PDF p.7, Methods |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `reported_with_caveat` | Exponentially rising/falling intensity; exact gain file not supplied. | PDF p.7, Methods |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `reported` | Audio-tactile target rows plus auditory-only catches; no tactile-only baseline reported. | PDF p.7, Methods |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `reported` | Random row combination, randomly intermingled with catches, split into two blocks. | PDF p.7, Methods |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `reported_with_caveat` | DS7A electrical tactile stimulation on dorsal upper arm; participant current table not reported. | PDF p.7, Methods |
| `segment_3_tactile_soa_baseline` | `soa_table` | `reported` | T1-T5 = 300, 800, 1500, 2200, 2700 ms from sound onset. | PDF p.7, Methods |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `reported_absent` | No tactile-only baseline rows reported for this task. | PDF p.7, Methods |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `reported` | Auditory-only catch rows with no tactile target. | PDF p.7, Methods |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `reported` | 8 target stimuli per T1-T5 x IN/OUT cell. | PDF p.7, Methods |
| `segment_4_counts` | `catch_count` | `reported` | 76 auditory-only catch rows. | PDF p.7, Methods |
| `segment_4_counts` | `block_count` | `reported` | Two blocks. | PDF p.7, Methods |
| `segment_4_counts` | `total_trial_count` | `source_inconsistency_caveat` | Runnable contract uses 156 rows: 80 target plus 76 catch. | PDF p.7, Methods |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
