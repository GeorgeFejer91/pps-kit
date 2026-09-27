# Canzoneri et al. (2013a)

- Record ID: `canzoneri_2013_tool_use_reshaping`
- DOI: `10.1007/s00221-013-3532-2`
- DOI URL: https://doi.org/10.1007/s00221-013-3532-2
- Coverage category: `covered_runnable_profile` after 2026-07-16 known-parameter review
- Task family: Canzoneri-style dynamic IN/OUT audio-tactile PPS assessment around tool-use training
- PDF status: `needs_user_download`; public full-text route reviewed, but no PDF is committed
- Supplement status: `not_found_or_not_needed_for_minimum_assessment_profile`
- Metadata confidence: `0.84` (`high_confidence_extraction_with_protocol_lineage`)
- Manual review: `manual_reviews/canzoneri_2013_tool_use_reshaping.json`

## Source Checks

- `Consensus MCP exact-title/DOI search 2026-07-16`: confirmed paper identity and abstract-level expected outcome.
- `Springer DOI page`: checked article metadata, DOI, journal, date, and abstract.
- `ResearchGate author-uploaded public full text`: checked Experiment 1A methods, tool-use training, results, Figure 3 caption, and Experiment 3 pointing-control text.
- `manual_reviews/canzoneri_2012_dynamic_sounds.json`: checked as protocol lineage because the 2013 paper says the audio-tactile task procedures were similar to Canzoneri et al. (2012).

## Closed Prior Gap

- Prior blocker: `exact trial count and ITI table`.
- Resolution: the 2013 paper directly reports the PPS assessment stimulus/timing frame and 60% tactile-target / 40% auditory-only catch ratio; the delegated 2012 protocol supplies the runnable count and block arithmetic. The profile now uses one assessment instance with 188 rows: 80 T1-T5 audio-tactile targets, 32 T0/T6 tactile-only baselines, 76 auditory-only catches, split into two 94-row blocks.

## Minimum Recreated Parameters

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `reported` | 3000 ms pink noise | 2013 Experiment 1A methods |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `reported` | IN/approaching and OUT/receding | 2013 Experiment 1A methods |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `reported` | near loudspeaker by forearm; far loudspeaker about 100 cm away | 2013 Experiment 1A methods and Fig. 1A |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `protocol_lineage_reported` | mirrored Canzoneri-family dynamic intensity envelope; exact SoundForge files unavailable | 2012 manual review |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `reported` | respond vocally to tactile target and ignore sound | 2013 Experiment 1A methods |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `reported` | 1000 ms pre-sound and 1000 ms post-sound silence; no variable ITI reported | 2013 Experiment 1A methods |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `reported` | tactile stimulus on hairy surface of right forearm | 2013 Experiment 1A methods |
| `segment_3_tactile_soa_baseline` | `soa_table` | `reported` | T1-T5 at 300/800/1500/2200/2700 ms after sound onset | 2013 Experiment 1A methods |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `protocol_lineage_reported` | T0/T6 tactile-only baseline rows | 2012 manual review |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `reported` | auditory-only catch trials | 2013 Experiment 1A methods |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `protocol_lineage_reported` | 8 repetitions per timing/direction | 2012 manual review |
| `segment_4_counts` | `catch_count` | `protocol_lineage_reported` | 76 catches per assessment | 2012 manual review, consistent with 2013 40% catch ratio |
| `segment_4_counts` | `block_count` | `protocol_lineage_reported` | 2 assessment blocks | 2012 manual review |

## Expected Outcome

- Tool-use is expected to shift the fitted PPS boundary toward farther auditory locations and change forearm body-representation metrics.
- The pointing-control experiment is not expected to produce the same PPS/body-representation shift.
- The runner validation can compare observed emulated task behavior against the extracted parameter contract, not against human PPS plasticity.

## Current Caveats

- Exact original SoundForge pink-noise samples and gain/envelope files are not available.
- Exact loudspeaker model, room transfer, and physical SPL calibration route are not fully reported.
- Participant-level electrical threshold/current calibration and voice-key threshold/latency are not physically validated.
- The profile recreates the audio-tactile PPS assessment. The 20-minute tool-use and pointing-control interventions remain physical/context procedures and are not automated runner phases.

Do not paste long source text here; use short page/section pointers and concise paraphrases.
