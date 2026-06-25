# Audiotactile PPS Literature Coverage Audit

Status: coverage audit for deciding whether the PPS Toolkit generalizes as a standardized tool for published audiotactile PPS task variants. This is not a GUI change.

## Scope

This audit asks one question: can the audiotactile PPS task itself be represented as a toolkit profile?

Clinical population, intervention, social, locomotion, VR, prosthesis, or emotional-condition context is not a blocker unless it changes the auditory stimulus, tactile stimulus, response rule, timing, trial family, spatial coordinate system, or apparatus geometry used by the PPS task.

For profile acceptance, the required published/task parameters are narrower than a full methods clone and must be complete through Segment 0-4: profile metadata/provenance, stimulus type and asset provenance, trajectory, Segment 2 trial sequence including ITI or jitter boxes when task-relevant, SOAs or distance-at-tactile values, baseline strategy/timing, and trial repetition count. Routine trial randomization, block order, Segment 5 block generation, and Segment 6 runner handoff are standard toolkit-native behavior rather than publication rejection criteria.

The machine-readable source is `assets/preloads/audiotactile_literature_coverage.json`.
The Holmes consensus-corpus screening trail is `assets/preloads/audiotactile_holmes2020_consensus_screening.json`.
The PubMed screening audit trail is `assets/preloads/audiotactile_pubmed_screening.json`, with the supplemental PubMed query-variant trail in `assets/preloads/audiotactile_pubmed_query_variant_screening.json`.
The OpenAlex broad-screen trail is `assets/preloads/audiotactile_openalex_broad_screening.json`, with per-hit screening decisions in `assets/preloads/audiotactile_openalex_candidate_screening.json`. The additional query-variant exhaustiveness screen is `assets/preloads/audiotactile_openalex_query_variant_screening.json`. The live web sanity trail is `assets/preloads/audiotactile_web_sanity_screening.json`.

Current ledger size: 74 literature records. Across the separate preload gate, 8 profile variants currently pass runnable checks. In the broader literature ledger, 29 not-yet-templated records expose toolkit-structure gaps, 21 not-yet-templated records are structurally close but lack extracted/published PPS-task parameters, and 5 records are adjacent/out of scope. The previous generic candidate bucket is now cleared: tracked records are classified by whether the PPS task is runnable, missing exact task details, blocked by an unsupported task structure, or not actually an audiotactile PPS target.

## Evidence Base

The consensus anchor is Holmes et al. (2020), which reports a systematic review/meta-analysis of audiotactile PPS-style tasks and identifies 23 articles and 46 relevant experiments. The local audit also screened PubMed on 2026-06-13 with `("audio-tactile" OR audiotactile) AND "peripersonal space"` and captured 48 records, including 25 post-2020 records.

Primary sources and artifacts:

- Holmes et al. (2020), Experimental Brain Research: https://doi.org/10.1007/s00221-020-05771-5
- Holmes consensus screening decisions: `assets/preloads/audiotactile_holmes2020_consensus_screening.json`
- PubMed search summary: `artifacts/literature_audit/pubmed_audio_tactile_pps_summary.json`
- PubMed screening decisions: `assets/preloads/audiotactile_pubmed_screening.json`
- PubMed query-variant search summary: `artifacts/literature_audit/pubmed_query_variant_search.json`
- PubMed query-variant source records: `artifacts/literature_audit/pubmed_query_variant_records.json`
- PubMed query-variant screening decisions: `assets/preloads/audiotactile_pubmed_query_variant_screening.json`
- Holmes supplement snapshots: `artifacts/literature_audit/holmes_2020_MOESM*.ods`
- OpenAlex sanity-route snapshot: `artifacts/literature_audit/openalex_audiotactile_pps_queries.json`
- OpenAlex broad-screen summary: `assets/preloads/audiotactile_openalex_broad_screening.json`
- OpenAlex per-hit candidate screen: `assets/preloads/audiotactile_openalex_candidate_screening.json`
- OpenAlex query-variant full-results summary: `artifacts/literature_audit/openalex_query_variant_full_results.json`
- OpenAlex query-variant screening decisions: `assets/preloads/audiotactile_openalex_query_variant_screening.json`
- Live web sanity screening decisions: `assets/preloads/audiotactile_web_sanity_screening.json`
- PubMed source records for the early auditory-tactile extinction papers: `artifacts/literature_audit/pubmed_variant_source_records.xml`

## Holmes Consensus Corpus Accountability

Holmes et al. (2020) is the consensus anchor for the older literature. The article reports 23 articles and 46 relevant experiments; the parsed supplement table yielded 49 experiment rows, with three extra rows treated as reference/parser artifacts rather than additional PPS-task requirements. The consensus screening file links each relevant experiment family to the coverage ledger or to an existing/current template status.

## PubMed Screen Accountability

The PubMed screen is fully accounted for in the machine-readable screening file: 48 records were screened, and every included record links to a literature-record ID in the coverage ledger. The screen produced these initial screening decisions; the final coverage ledger then resolves candidate-like hits into missing-parameter, structural-gap, or adjacent/out-of-scope categories:

| Screen decision | Count |
|---|---:|
| Current runnable profile | 4 |
| Current blocked profile | 6 |
| Included task needing exact PPS-task extraction | 22 |
| Candidate requiring toolkit structure | 6 |
| Candidate requiring static near/far support | 1 |
| Duplicate correction | 1 |
| Review/theory/commentary/methods-only exclusion | 5 |
| Adjacent non-PPS or non-audiotactile exclusion | 3 |

The count of runnable PubMed records is lower than the runnable published-template count because the 2026 Lamia paper maps to two runnable experiment variants in the toolkit. Across the whole screen, 39 records are included/current/candidate-like PPS task records and 9 are exclusions, duplicate corrections, or adjacent non-task hits.

An OpenAlex title/abstract sanity route was also run with broader queries. It confirmed several existing records, corrected the Ferri 2015, Galli 2015, and PNAS interoception/exteroception DOI/source mappings, and added or checked `social_perception_2017`, `lower_limb_pps_2017`, `newborn_boundaries_2019`, `ronga_2021_newborn_erp`, `ferri_2015_jneurosci_itv`, `taffou_2021_auditory_roughness`, `novel_two_phase_audio_tactile_2025`, and `looming_duration_2025`. A follow-up pass promoted `serino_2018_mixed_reality_pps`, `amemiya_2017_pseudowalking_footsole`, and `serino_2011_professional_fencers`, linked obvious preprint/source/duplicate hits to existing records, and retained the lower-limb record as an adjacent false positive after source checking because it uses a visuo-tactile lower-limb task rather than an audiotactile PPS task. The main OpenAlex broad route retrieved all 755 records for `audio-tactile peripersonal space`; its automated candidate triage is stored at `artifacts/literature_audit/openalex_broad_candidate_triage.json` and now links 47 of 103 candidate-like hits to coverage records. The remaining 56 candidate-like hits are explicitly screened in `assets/preloads/audiotactile_openalex_candidate_screening.json` as visual-tactile/non-auditory, auditory-only/no-tactile, non-PPS audiotactile/haptic, review/model/theory, or grey-literature/source records rather than unresolved tasks.

A later query-variant pass searched `audio-tactile`, `audiotactile`, `auditory-tactile`, `auditory tactile`, `vibrotactile`, `looming sound`, and `sounds near the hand` wording through OpenAlex, retrieving the complete result set for each query. It screened 22 candidate-like hits from 822 unique returned records. This promoted `ladavas_2001_auditory_tactile_extinction` and `farne_ladavas_2002_auditory_pps_humans`, linked eight existing records or duplicate/source rows, and excluded 12 review, visual-tactile, nonhuman, visual-feedback, or metadata/reference hits. This pass is what added the early auditory-tactile extinction task family to the standardization gap list.

A supplemental PubMed query-variant pass searched eight auditory-tactile, vibrotactile, looming-sound, near-hand, and auditory-PPS phrasings. It returned 70 unique PMIDs; after subtracting the original 48-record PubMed screen, 22 supplemental PMIDs were manually screened. This promoted `teramoto_2013_beyond_head_audiotactile`, `finisguerra_2015_moving_sounds_motor`, and `biggio_2017_racket_tool_use`, linked six records to existing ledger rows, and excluded 13 adjacent, review/theory, auditory-only, non-PPS, or conditioning/drug-context records.

A live web sanity pass checked eight currently visible search hits and full-text/PDF pages. It linked the Bernasconi/Noel iEEG trunk task, the 2026 consciousness-state task, Teraoka et al. (2024 front/rear), Tonelli et al. (2019 echolocation), and Pfeiffer et al. (2018 vestibular/peri-head) to existing ledger rows, updated `looming_duration_2025` from a missing-parameter record to a toolkit-structure gap after the PDF exposed the SOA/repetition/catch/tactile parameters, excluded Occelli et al. (2011) as a review rather than a distinct task profile, and added Barumerli et al. (2026 semantic looming) as an adjacent auditory-only PPS record rather than an audiotactile task.

## Current Toolkit Verdict

The current profile gate covers 22 templates:

| Outcome | Count | Meaning |
|---|---:|---|
| GUI-recreatable | 7 | Current Segment 0-4 profile parameters are complete; Segment 5-6 are native toolkit generation/handoff. Six are published profiles; the canonical Study 5 white/pink profile is the unpublished lab profile. |
| Missing publication parameters | 12 | The task looks structurally expressible, but published or encoded details are insufficient. |
| Toolkit structural gap | 7 | The task uses a trial, audio, tactile, response, timing, coordinate, or apparatus feature that the toolkit schema does not yet model. |

Runnable published-paper profiles today:

- `matsuda_2021_four_directions`
- `barumerli_2026_arm_movement_exp1`
- `barumerli_2026_arm_movement_exp2`
- `noel_2015_bodily_self`
- `pfeiffer_2018_lateral_perihead_left_to_right`
- `serino_2015_peri_trunk_exp1`

The stable template IDs `barumerli_2026_*` are retained, but the citation now follows the corrected 2026 author listing: Lamia, Shabani, and Candidi.

## Per-Record Verdict Ledger

This table is generated from `assets/preloads/audiotactile_literature_coverage.json` so the human report has one visible verdict per tracked record (74 rows). Context such as participant group, clinical state, intervention, social manipulation, VR, locomotion, or expertise is only listed as a blocker when it changes the audiotactile PPS task execution itself.

| Study | Audiotactile task family | Verdict | Task-mechanics reason |
|---|---|---|---|
| LÃ davas et al. (2001) | near/far auditory-tactile extinction task around the head in a right-brain-damaged patient | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `body_part_anchored_coordinate_frames`, `cross_modal_extinction_response_mapping` Missing/extract: extract exact near/far sound distances, sound types, tactile site and response scoring, trial counts, and clinical extinction-response procedure before any scaffolded profile |
| FarnÃ¨ & LÃ davas (2002) | front/back near/far auditory-tactile extinction task around the head in right-brain-damaged patients | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `body_part_anchored_coordinate_frames`, `cross_modal_extinction_response_mapping` Missing/extract: extract front/back and near/far auditory positions, pure-tone versus complex-sound settings, tactile site and response scoring, trial counts, and extinction-response procedure before templating |
| Kitagawa et al. (2005) | static near/far audio-tactile sound-complexity task | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `tactile_discrimination_or_localization_response` Missing/extract: full exact timing, response mapping, and stimulus asset details need extraction |
| Serino et al. (2007) | static near/far weak-target Go/NoGo tactile detection | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `weak_strong_no_target_gonogo`, `voice_key_response_capture`, `electrical_tactile_calibration` Missing/extract: full calibration and response-capture implementation details need extraction |
| Serino et al. (2009) | audio-tactile PPS stimulation with TMS/MEP endpoint | Not templated; toolkit structure gap | Toolkit/task constraints: `external_event_trigger_sync_contract`, `static_near_far_trial_family` Missing/extract: requires full task-method extraction if we later support neurophysiology trigger profiles |
| Tajadura-Jimenez et al. (2009) | auditory, tactile, and audiotactile lateralization with crossed/uncrossed posture | Not templated; toolkit structure gap | Toolkit/task constraints: `tactile_discrimination_or_localization_response`, `body_part_anchored_coordinate_frames` Missing/extract: extract lateralization response mapping, posture/body-coordinate rules, and stimulus timing |
| Bassolino et al. (2010) | static near/far tactile detection around hand/tool space | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `weak_strong_no_target_gonogo` Missing/extract: full trial counts, tactile calibration, and response mapping need extraction |
| Serino et al. (2011) | static near/far audio-tactile PPS task with rTMS context | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `weak_strong_no_target_gonogo` Missing/extract: full audio, tactile, and response settings need extraction |
| Avenanti et al. (2012) | audio-tactile PPS stimulation with motor-evoked-potential endpoint | Not templated; toolkit structure gap | Toolkit/task constraints: `external_event_trigger_sync_contract` Missing/extract: not a standalone behavioral tactile RT profile in the current toolkit |
| Serino et al. (2011 professional fencers) | audio-tactile PPS task around the right hand while holding a fencing weapon or short handle | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: conference abstract reports an audio-tactile right-hand PPS task but not enough timing, distance, tactile, response, trial-count, and weapon/handle geometry parameters for a runnable profile |
| Canzoneri et al. (2012) | canonical dynamic looming/receding sound with tactile detection | Template exists; toolkit structure gap | Toolkit/task constraints: `direction_coupled_tactile_only_baseline`, `exact_audio_envelope_or_gain_files`, `voice_key_response_capture`, `electrical_tactile_calibration` Missing/extract: exact original SoundForge gain/envelope files; voice-key response capture; electrical tactile threshold calibration |
| Canzoneri et al. (2013a) | Canzoneri-style dynamic PPS task | Template exists; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact trial count and ITI table |
| Canzoneri et al. (2013b) | Canzoneri-style dynamic PPS task | Template exists; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters`, `electrical_tactile_calibration` Missing/extract: exact trial count and tactile calibration table |
| Cimmino et al. (2013) | static near/far audio-tactile PPS task | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `weak_strong_no_target_gonogo` Missing/extract: full audio/tactile/timing parameters need extraction |
| Teramoto et al. (2013) | auditory/tactile/audiotactile information processing with tactile response mapping | Not templated; toolkit structure gap | Toolkit/task constraints: `tactile_discrimination_or_localization_response`, `static_near_far_trial_family` Missing/extract: full response mapping, stimulus timing, and apparatus details need extraction |
| Teneggi et al. (2013) | face tactile detection with approaching/receding sound labels | Template exists; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact distance/timing table from supplement |
| Taffou & Viaud-Delmon (2014) | rear-field dog/sheep audio-tactile PPS task | Template exists; toolkit structure gap | Toolkit/task constraints: `rear_hemifield_trajectory_families`, `ecological_or_licensed_audio_assets`, `hrtf_database_or_binaural_engine_mismatch` Missing/extract: exact dog/sheep audio; LISTEN HRTF provenance |
| Ferri et al. (2015A) | dynamic emotional artificial looming sounds with tactile detection | Template exists; missing task parameters | Toolkit/task constraints: `exact_audio_envelope_or_gain_files` Missing/extract: exact auditory files; paper-specific gain envelope |
| Ferri et al. (2015B) | dynamic ecological emotional sounds with tactile detection | Template exists; missing task parameters | Toolkit/task constraints: `ecological_or_licensed_audio_assets`, `exact_audio_envelope_or_gain_files` Missing/extract: licensed ecological sounds; exact amplitude envelopes |
| Ferri et al. (2015), JNeurosci | approaching auditory stimuli plus tactile RT PPS boundary task with fMRI endpoint | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact behavioral audio-tactile PPS timing, distances, response settings, and auditory trajectory; fMRI/BOLD endpoint is non-blocking for audiotactile recreation |
| Galli et al. (2015) | front/back trunk tactile PPS with dynamic auditory field | Template exists; toolkit structure gap | Toolkit/task constraints: `gaussian_speaker_array_amplitude_field` |
| Maister et al. (2015) | PPS measurement after shared sensory/social context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact audiotactile PPS timing, distances, trial counts, tactile settings, and response settings; shared sensory/social context is non-blocking |
| Noel et al. (2015a) | chest tactile PPS with looming sound | GUI-recreatable now | Current profile passes the Segment 0-4 audiotactile recreation gate. |
| Noel et al. (2015b) | walking/full-body PPS audio-tactile task | Template exists; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact sound distances and trial counts |
| Serino et al. (2015), Exp. 1 | trunk tactile PPS with two-speaker analog looming/receding setup reconstructed as a binaural trajectory | GUI-recreatable now | Current profile passes the Segment 0-4 audiotactile recreation gate. |
| Serino et al. (2015), Exp. 2 | front/back trunk tactile PPS with physical speaker array | Template exists; toolkit structure gap | Toolkit/task constraints: `multi_speaker_array_switching`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: 13-distance internal schedule |
| Serino et al. (2015), Exp. 3 | hand tactile PPS with lateralized hand coordinate | Template exists; toolkit structure gap | Toolkit/task constraints: `body_part_anchored_coordinate_frames` |
| Serino et al. (2015), Exp. 4-6 | additional body-part/front-back PPS variants from the same six-experiment paper | Not templated; toolkit structure gap | Toolkit/task constraints: `body_part_anchored_coordinate_frames`, `multi_speaker_array_switching` Missing/extract: experiment-specific distance, tactile-site, and apparatus mappings need extraction |
| Serino/Canzoneri 2015 toolless sync training | bimodal IN/OUT target trials plus auditory-only catch trials | Template exists; missing task parameters | Toolkit/task constraints: `voice_key_response_capture`, `electrical_tactile_calibration` Missing/extract: electrocutaneous tactile calibration; voice-key response capture |
| Ardizzi & Ferri (2018) | dynamic audio-tactile PPS boundary task with interoception context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact audio-tactile PPS task scaffold, timing, distances, tactile settings, response settings, and analysis parameters; interoception context is non-blocking |
| Hobeika et al. (2018) | lateral PPS audio-tactile task linked to handedness | Not templated; toolkit structure gap | Toolkit/task constraints: `body_part_anchored_coordinate_frames`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact lateral trajectory, timing, and tactile-site mapping need extraction |
| Noel et al. (2018) | psychophysical-computational PPS resizing task | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract velocity levels, peri-face/peri-trunk mapping, timing, tactile settings, response settings, and whether the psychophysical task reuses an existing dynamic PPS scaffold |
| Pfeiffer et al. (2018) | bilateral lateral peri-head PPS trajectory profile | GUI-recreatable now | Current profile passes the Segment 0-4 audiotactile recreation gate. |
| Bernasconi/Noel et al. (2018) | approaching auditory stimuli plus trunk tactile stimulation during iEEG | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact approaching-sound trajectory, far/intermediate/close tactile timings, trunk tactile apparatus, and response/event settings; iEEG endpoint is non-blocking for audiotactile recreation |
| Tonelli et al. (2019) | seven-speaker audio-tactile PPS task | Template exists; toolkit structure gap | Toolkit/task constraints: `multi_speaker_array_switching` Missing/extract: apparatus-specific seven-speaker switching/timing details |
| Pregnancy PPS study (2019) | audio-tactile PPS measurement in pregnancy context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact audio-tactile PPS timing, distances, trial counts, and response settings; pregnancy context is non-blocking |
| Identifying PPS boundaries in newborns (2019) | newborn audio-tactile PPS boundary task with sound-intensity/distance and tactile response measures | Not templated; toolkit structure gap | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters`, `static_near_far_trial_family` Missing/extract: extract auditory intensity/distance levels, tactile timing, response measure, and infant-specific apparatus separately from participant age |
| Spatial tuning of multisensory responses in newborns (2021) | near/far auditory plus electrical tactile stimulation with ERP endpoint | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `electrical_tactile_calibration`, `external_event_trigger_sync_contract` Missing/extract: extract near/far auditory apparatus, electrical tactile parameters, timing offset, and ERP trigger needs |
| Altered bodily self-consciousness and PPS in autism (2019) | audio-tactile PPS measurement in autism context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact task parameters need extraction; clinical context is non-blocking |
| PPS encoding in disorders of consciousness (2019) | audio-tactile PPS task with neuroclinical endpoint | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `external_event_trigger_sync_contract`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract 5 cm/75 cm auditory-tactile timing, tactile apparatus, response/EEG triggers, and task execution separately from clinical endpoint |
| Social coding of multisensory space (2019) | audio-tactile PPS measurement in social context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact task parameters need extraction; social context is non-blocking |
| Social perception shapes multisensory PPS (2017) | audio-tactile PPS task with social-perception context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract the core audio-tactile PPS task parameters; social perception context is non-blocking |
| Lower-limb PPS boundaries (2017) | visuo-tactile lower-limb PPS boundary task, not an audiotactile PPS task | Adjacent/out of scope | Missing/extract: source check reports a visuo-tactile lower-limb task; retain as adjacent exclusion, not a toolkit integration target |
| Foot-sole vibration PPS remapping (2019) | looming-sound PPS tactile-processing task with foot-sole vibration context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract the core audio-tactile PPS timing, distances, trial counts, and response settings separately from the foot-sole vibration manipulation |
| Hobeika et al. (2020) | expectancy-controlled dynamic PPS task with sound-propagation corrections | Not templated; toolkit structure gap | Toolkit/task constraints: `fixed_iti_or_hazard_control_policy`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract logarithmic distances, fixed-distance baselines, and sound-propagation settings |
| Tool-use observation PPS (2020) | audio-tactile PPS task around tool-use observation | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract whether PPS task differs from Canzoneri-style dynamic scaffold |
| Spadone et al. (2021) | fMRI audio-tactile task with looming/flat and near/far conditions | Not templated; toolkit structure gap | Toolkit/task constraints: `fixed_iti_or_hazard_control_policy`, `external_event_trigger_sync_contract` Missing/extract: extract near/far, flat/dynamic, and fMRI block timing separately from scanner context |
| How ageing shapes body and space representations (2021) | audio-tactile PPS task in ageing context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: exact task parameters need extraction; age group context is non-blocking |
| Seeming confines (2021) | audio-tactile PPS remapping after tool-use with electrophysiology | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract PPS task timing, distances, tactile settings, response rules, and trial repetition counts separately from electrophysiology; electrophysiology context is non-blocking unless trigger timing changes task execution |
| Jazz duet PPS (2021) | audio-tactile PPS task after musical interaction context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract the audiotactile PPS task parameters separately from the musical-interaction manipulation; music/social context is non-blocking unless it changes the task audio assets |
| Taffou et al. (2021) | rear-hemifield looming rough/non-rough sound with speeded tactile detection | Not templated; toolkit structure gap | Toolkit/task constraints: `rear_hemifield_trajectory_families`, `hrtf_database_or_binaural_engine_mismatch`, `exact_audio_envelope_or_gain_files` Missing/extract: extract exact rough/non-rough sound synthesis, binaural rendering filters, rear trajectory implementation, and tactile/response timing before templating |
| Holmes et al. (2020), four experiments | static near/far sounds paired with weak vibrotactile targets and Go/NoGo response logic | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `weak_strong_no_target_gonogo` Missing/extract: task is publicly documented but needs translation into a static near/far toolkit profile |
| Tool-use extends PPS boundaries in schizophrenia (2022) | audio-tactile PPS task before/after tool-use | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract PPS task parameters; clinical group and tool-use context are non-blocking |
| Teraoka et al. (2024) | front/rear approaching auditory probe with vibrotactile detection and baseline | Not templated; toolkit structure gap | Toolkit/task constraints: `body_part_anchored_coordinate_frames`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract auditory-probe trajectory, baseline structure, and apparatus geometry |
| Body image and social cognition PPS task (2024) | audio-tactile reaction-time PPS boundary task used alongside interpersonal-distance measures | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact audio-tactile reaction-time task parameters; body-image/social-cognition variables are non-blocking context |
| Mindfulness and PPS boundaries (2024) | audio-tactile PPS boundary task around focused-attention meditation context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract exact audio-tactile PPS task timing, distances, trial counts, and response settings; meditation context is non-blocking unless it changes trial execution |
| Serino et al. (2018 mixed reality) | mixed-reality PPS task using visual or audiovisual looming stimuli paired with tactile detection | Not templated; toolkit structure gap | Toolkit/task constraints: `audiovisual_or_trisensory_trial_family`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract whether audio-only trials are available separately from audiovisual trials, the acoustic stimulus/rendering details, tactile timing, response settings, MR apparatus synchronization, and trial counts before deciding whether an audio-tactile-only scaffold is honest |
| Amemiya et al. (2017 pseudo-walking foot-sole vibration) | looming-sound chest-vibrotactile detection PPS readout with pseudo-walking foot-sole vibration context | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract core looming-sound timing/distance profile, chest vibrotactile target timing, response settings, trial counts, and whether the foot-sole vibration context must be represented as a secondary tactile condition for exact task execution |
| Self and PPS two-phase audio-tactile paradigm (2025) | two-phase audio-tactile PPS paradigm for defensive boundaries | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: bibliographic identity and full task parameters need verification before templating |
| Impact of looming sound duration on PPS measurement (2025) | looming-cue tactile-response PPS task varying auditory duration | Not templated; toolkit structure gap | Toolkit/task constraints: `tactile_waveform_frequency_profile`, `hrtf_database_or_binaural_engine_mismatch` Missing/extract: live PDF check reports 2 s/3 s right-lateral looming pink-noise tasks, seven SOAs per duration, 16 repetitions per delay/condition, 21 auditory-only catch trials, 80 Hz 200 ms sawtooth tactile stimulation, response button, starting distances, and speed; exact original MATLAB HRTF implementation and tactile-waveform profile are not current first-class toolkit inputs |
| Lost in time and space? (2024) | audio-tactile PPS and time-perception task | Not templated; missing task parameters | Toolkit/task constraints: `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: determine PPS-task parameters separately from time-perception measures |
| Functional organization of rear/front PPS (2025/2026) | distance-dependent audio-tactile integration in rear and front spaces | Not templated; toolkit structure gap | Toolkit/task constraints: `body_part_anchored_coordinate_frames`, `rear_hemifield_trajectory_families`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract front/rear sound-spatialization method, distance levels, tactile timing, and body-relative trajectory mappings |
| Interoception vs. Exteroception (2025) | audio-tactile self-relevance task placing the auditory source inside versus outside PPS with tactile responses and EEG/HEP endpoint | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `external_event_trigger_sync_contract`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract auditory inside/outside-PPS locations, tactile timing, response window, and EEG/HEP trigger timing requirements |
| Multisensory integration in PPS indexes consciousness states (2026) | audio-tactile PPS task in sleep/disorders-of-consciousness setting | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract near/far audiotactile stimulus distances, tactile settings, timing, trial counts, response/trigger settings, and apparatus details independently of sleep or clinical endpoint |
| Matsuda et al. (2021) | front, rear, left, and right approaching/receding audio-tactile PPS task | GUI-recreatable now | Current profile passes the Segment 0-4 audiotactile recreation gate. |
| Lerner et al. (2021) | VR 3D audio-tactile PPS boundary estimation | Template exists; toolkit structure gap | Toolkit/task constraints: `body_scaled_distance_units`, `unity_3d_tune_in_engine_behavior` Missing/extract: exact Unity/3D Tune-In stimulus engine behavior |
| Lamia, Shabani, & Candidi (2026) | looming/receding audio-tactile task with arm-movement context | GUI-recreatable now | Current profile passes the Segment 0-4 audiotactile recreation gate. |
| Using Android smartphones to collect RTs to multisensory stimuli (2025) | methods/device paper rather than a distinct PPS profile | Adjacent/out of scope | Excluded or adjacent to this audit target. |
| Spiousas et al. (2025) | auditory reachability judgments without tactile stimulus/response | Adjacent/out of scope | Excluded or adjacent to this audit target. |
| Barumerli et al. (2026 semantic looming) | auditory looming-distance and motor-preparation task without tactile stimulus/response | Adjacent/out of scope | Excluded or adjacent to this audit target. |
| Rossi Sebastiano et al. (2022) | visuo-tactile PPS task, not an audio-tactile profile | Adjacent/out of scope | Excluded or adjacent to this audit target. |
| Teramoto et al. (2013 beyond head) | audiotactile interaction task manipulating cheek, hand, and knee tactile sites with spatially related sounds | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `body_part_anchored_coordinate_frames`, `tactile_discrimination_or_localization_response` Missing/extract: extract exact body-site mapping, auditory locations, tactile response/scoring rules, timing, and trial counts before templating |
| Finisguerra et al. (2015) | moving-sound hand-PPS task with rare tactile targets and motor-system/TMS endpoint | Not templated; toolkit structure gap | Toolkit/task constraints: `voice_key_response_capture`, `external_event_trigger_sync_contract`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract moving-sound trajectory, tactile target schedule, vocal response capture, TMS/MEP trigger timing, baseline timing strategy, and trial counts before templating |
| Biggio et al. (2017) | near/far audio-tactile PPS task while tennis players or novices hold a racket | Not templated; toolkit structure gap | Toolkit/task constraints: `static_near_far_trial_family`, `voice_key_response_capture`, `missing_core_soa_iti_baseline_repetition_parameters` Missing/extract: extract near/far auditory locations, tactile site/timing, verbal response capture, racket/handle geometry, conditions, and trial counts before templating; sport expertise is non-blocking context |

## What Counts As A Real Toolkit Constraint

These are the main standardization constraints to flag when deciding whether the toolkit can capture the literature:

| Gap group | What the check asks |
|---|---|
| Trial design families | Can the profile express the original task's audio-tactile, tactile-only, auditory-only, catch, Go/NoGo, baseline, and target-present/target-absent rules? |
| Audio source and renderer | Can the profile represent the actual auditory element: generated tone/noise, ecological or licensed audio, HRTF/binaural renderer, physical multi-speaker array, exact gain envelope, or amplitude field? |
| Spatial coordinate system | Can the profile encode body-relative, body-scaled, hand/head/trunk/rear-field, hemifield, or apparatus-relative coordinates? |
| Tactile and response mapping | Can the profile represent tactile modality, body site, output channel, duration, calibration, response modality, and response rule rather than assuming simple button detection? |
| Timing and repetition | Can the profile encode the exact SOA/distance table, ITI or jitter policy, baseline timing strategy, trial repetition count, and any hazard/expectancy control implemented through PPS-task timing? |
| External trigger contract | If physiology is part of the task execution, can the profile preserve required event triggers and timing without treating the clinical or neurophysiology endpoint itself as a blocker? |

| Constraint | Why it matters | Current examples |
|---|---|---|
| Static near/far trial family | Older APPS studies present sounds from fixed near/far speakers rather than generated looming trajectories. | Kitagawa 2005; Serino 2007; Bassolino 2010; Cimmino 2013 |
| Weak/strong/no-target Go/NoGo | Several early tasks use weak targets, strong non-targets, no-target catch trials, and vocal response rules. | Serino 2007; Holmes 2020 experiments |
| Audiovisual/trisensory trial family | Some PPS readouts combine visual or audiovisual looming stimuli with tactile targets; exact replication needs a visual/audiovisual stimulus slot rather than pretending it is pure audiotactile. | Serino 2018 mixed-reality task |
| Tactile discrimination/localization response | Some studies are not simple speeded tactile detection tasks. | Kitagawa 2005; Teramoto 2013 |
| Cross-modal extinction response mapping | Early neuropsychological auditory-PPS studies use auditory-tactile extinction/neglect-style response scoring rather than speeded tactile RT. | LÃ davas 2001; FarnÃ¨ & LÃ davas 2002 |
| Direction-coupled tactile-only baselines | Baseline timing may be tied to omitted sound positions such as T0/T6. | Canzoneri 2012 |
| Core SOA, ITI, baseline, and repetition parameters | Missing SOA/distance, ITI/jitter, baseline timing, or trial-repetition values prevent honest profile checks even when the structure is otherwise compatible. Randomization and block order alone do not. | Canzoneri 2013; Teneggi 2013; Noel 2015 walking |
| Analog two-speaker apparatus provenance | Near/far speaker setups are original apparatus descriptions. They are not blockers by themselves when reported trajectory/timing/source parameters can be recreated with the binaural renderer; exact original gain/envelope files remain missing provenance when required for author-stimulus equivalence. | Canzoneri 2012; Serino 2015 peri-trunk/peri-hand |
| Multi-speaker array switching | A physical array may switch speakers or schedule discrete positions rather than render one virtual source. | Tonelli 2019; Serino 2015 front/back |
| Gaussian speaker-array amplitude field | The auditory source is an amplitude field across speakers. | Galli 2015 |
| HRTF or binaural engine mismatch | Exact HRTF database or renderer behavior can define the stimulus. | Taffou 2014 LISTEN HRTF; Pfeiffer reference simulator; Lerner Unity/3D Tune-In |
| Body-scaled distances | Distances depend on the participant's body dimensions rather than absolute cm/m. | Lerner 2021 |
| Body-part anchored coordinate frames | Space may be hand-, trunk-, head-, rear-, or hemifield-relative. | Serino 2015 hand; Hobeika 2018; Teraoka 2024 |
| Ecological/licensed audio | The original PPS-task sounds may be proprietary, ecological, emotional, animal, music, or voice stimuli. Contextual music/social material is not a blocker unless it is actually part of the audiotactile PPS stimulus. | Ferri 2015; Taffou 2014 |
| Voice-key response capture | Original response timing can be vocal rather than button/mouse. | Canzoneri 2012; Serino/Canzoneri training profile |
| Electrical tactile calibration | Exact pulse parameters and thresholding are required. | Canzoneri 2012; Serino/Canzoneri training profile |
| Tactile waveform/frequency profile | Some haptic stimuli are defined by waveform and frequency, not only site/channel/duration. | 2025 looming-duration proceedings |
| External event-trigger/sync contract | fMRI, EEG, iEEG, TMS/MEP, or sleep endpoints are not blockers for the PPS task. Flag only the required event-trigger timing or external synchronization contract when that contract is needed to recreate the audiotactile task execution. | Serino 2009; Avenanti 2012; EEG/fMRI tasks when trigger timing is part of the run contract |

## Current Profiles That Need Re-Audit

These are structurally close enough that the next step is mainly paper/supplement extraction:

| Profile | Missing task information |
|---|---|
| `canzoneri_2013_amputation_prosthesis` | Exact trial count and tactile calibration table. |
| `canzoneri_2013_tool_use_reshaping` | Exact trial count and ITI table. |
| `ferri_2015_artificial_looming_valence` | Exact artificial audio files and gain envelope. |
| `ferri_2015_ecological_looming_valence` | Licensed ecological source sounds and amplitude envelopes. |
| `noel_2015_walking_full_body_action` | Exact sound distances and trial counts. |
| `serino_2015_toolless_sync_training` | Electrical tactile calibration and voice-key response capture. |
| `teneggi_2013_social_face_pps` | Exact distance/timing table from the supplement. |

## Current Profiles That Need Toolkit Expansion

These already expose real standardized-toolkit gaps:

| Profile | Main unsupported task structure |
|---|---|
| `canzoneri_2012_dynamic_sounds` | Direction-coupled tactile-only T0/T6 baselines. |
| `tonelli_2019_echolocation` | Seven-speaker switching/timing. |
| `galli_2015_wheelchair_full_body` | Speaker-array Gaussian amplitude control. |
| `lerner_2021_3d_audio_tactile_boundary` | Body-scaled distance mode and Unity/3D Tune-In stimulus behavior. |
| `serino_2015_front_back_trunk_exp2` | Physical 16-speaker array plus internal distance schedule. |
| `serino_2015_peri_hand_exp3` | Lateralized hand coordinate. |
| `taffou_2014_cynophobic_rear_looming` | Separate rear-left/rear-right trajectory families plus exact ecological audio/HRTF provenance. |

## Known Literature Not Yet Templated

These records are in the consensus corpus, PubMed catch-up/search-variant routes, or OpenAlex broad/query-variant routes but are not yet represented as individual toolkit profiles:

| Study | Likely task family | Toolkit status |
|---|---|---|
| LÃ davas et al. 2001; FarnÃ¨ & LÃ davas 2002 | Near/far and front/back auditory-tactile extinction tasks around the head | Needs static near/far/front/back head-space support plus cross-modal extinction response/scoring support; clinical lesion status is context, but extinction-style response mapping is a real toolkit gap. |
| Kitagawa et al. 2005 | Static near/far audio-tactile sound-complexity task | Needs static near/far plus tactile discrimination/localization response support. |
| Serino et al. 2007 | Static near/far weak-target Go/NoGo tactile detection | Needs static near/far, weak/strong/no-target trial logic, voice response, and tactile calibration. |
| Serino et al. 2009; Avenanti et al. 2012 | Audio-tactile PPS stimulation with TMS/MEP endpoints | Not a standalone runner target unless physiology trigger timing becomes in scope. |
| Tajadura-Jimenez et al. 2009 | Auditory, tactile, and audiotactile lateralization with crossed/uncrossed posture | Needs tactile localization/discrimination responses and body-coordinate rules. |
| Bassolino et al. 2010; Cimmino et al. 2013 | Static near/far hand/tool-space PPS tasks | Needs static near/far task family and exact method extraction. |
| Serino et al. 2011 professional fencers | Audio-tactile right-hand PPS task with short-handle/weapon context | Need exact timing, distance, tactile, response, trial-count, and handle/weapon geometry parameters before templating; fencing expertise is non-blocking unless it changes task geometry. |
| Teramoto et al. 2013 beyond-head audiotactile interactions | Cheek/hand/knee auditory-tactile information processing beyond the head | Needs static near/far or body-site-linked trial families, body-part anchored coordinates, tactile discrimination/localization response support, and exact timing/site extraction. |
| Finisguerra et al. 2015 | Moving-sound hand-PPS task with rare tactile targets and vocal responses | Needs voice-key response capture, exact moving-sound trajectory/tactile-target timing, and any required external trigger contract separated from the TMS/MEP endpoint. |
| Biggio et al. 2017 | Near/far audio-tactile PPS task with racket/tool-use context | Needs static near/far support, voice-key response capture, exact tactile timing/trial counts, and task geometry extraction; sport expertise and tool-use group context are non-blocking unless they change apparatus geometry. |
| Maister et al. 2015; Ardizzi & Ferri 2018; Noel 2018 | Likely PPS measurement variants around social/interoceptive/computational contexts | Need exact PPS task timing, distances, tactile/response settings, and trial repetition counts; the surrounding context is non-blocking unless it changes task execution. |
| Holmes et al. 2020 four experiments | Static near/far sounds paired with weak vibrotactile targets and Go/NoGo logic | Needs static near/far and weak/strong/no-target task support. |
| Hobeika et al. 2018 | Lateral PPS/handedness task | Needs lateral body-coordinate extraction and exact timing/trajectory data. |
| Hobeika et al. 2020 | Expectancy/sound-propagation controlled dynamic PPS task | Needs hazard/expectancy controls, fixed-distance baselines, and propagation settings. |
| 2017 social-perception study; 2019 autism/social-coding studies | Likely standard audio-tactile PPS measurements in different groups or contexts | Need task-parameter extraction; group/social context is non-blocking unless it changes the core PPS task. |
| 2017 pseudo-walking foot-sole vibration and 2019 pregnancy/foot-sole-vibration studies; 2024 body-image and mindfulness studies | Structurally close audio-tactile PPS tasks | Need exact timing, distances, tactile settings, trial counts, and response settings before templating; secondary foot-sole vibration is context unless exact replication requires an extra tactile channel/condition. |
| 2025 looming-duration proceedings | Two-duration right-lateral looming pink-noise PPS task with tactile-only baseline and auditory-only catch trials | PDF reports enough SOA/repetition/catch/tactile timing to stop treating this as missing trial data, but exact recreation needs tactile waveform/frequency profile support and HRTF/rendering provenance handling. |
| 2019 newborn-boundary and disorders-of-consciousness studies; 2021 newborn ERP; 2025 interoception/exteroception PNAS paper | Static near/far or inside/outside PPS audio-tactile tasks with infant/EEG/clinical context | Need static near/far/inside-outside support plus task-specific apparatus/timing extraction; age, clinical state, and physiology endpoints are non-blocking context unless trigger timing is required. |
| 2015 JNeurosci fMRI paper; 2020-2022 tool-use/ageing/electrophysiology/social-music studies | Likely standard PPS scaffold with added context or physiology | Need extraction of exact PPS task timing, distances, tactile settings, response rules, and trial repetition counts. Tool-use, ageing, electrophysiology, clinical, and musical-interaction context is non-blocking unless it changes the audiotactile task stimuli or run contract. |
| Taffou et al. 2021 auditory roughness | Rear-hemifield rough/non-rough looming sound plus tactile detection | Needs rear-hemifield trajectory support, binaural/HRTF provenance, and rough/non-rough sound synthesis extraction. |
| Serino et al. 2018 mixed-reality PPS | Mixed-reality visual/audiovisual looming stimuli paired with tactile detection | Needs audiovisual/trisensory trial-family support or explicit extraction of any separable audio-tactile-only component. |
| 2024 depersonalisation/time-perception paper | Audio-tactile PPS plus time-perception measures | Need exact task extraction; time-perception context is non-blocking unless it changes trial execution. |
| Teraoka et al. 2024 | Front/rear approaching auditory probe plus vibrotactile detection | Needs apparatus geometry, baseline structure, and body-relative coordinate mapping. |
| 2025 two-phase audio-tactile paradigm | New self/non-self sound-association plus PPS measurement procedure | Need bibliographic verification and exact PPS-measurement parameters before templating. |
| 2025/2026 rear/front Cortex paper | Distance-dependent audio-tactile integration in rear and front spaces | Needs rear/front body-relative coordinate mapping plus exact timing and spatialization extraction. |
| 2026 consciousness-state paper | Static near/far audio-tactile PPS task in sleep/disorders-of-consciousness setting | Needs static near/far support plus exact near/far distances, tactile settings, timing, response/trigger settings, and apparatus details; sleep/clinical endpoint is non-blocking context. |

## Adjacent But Not Toolkit Profiles

Some search hits should not become audiotactile PPS preloads:

- Spiousas et al. 2025 is auditory reachability/peripersonal space without a tactile stimulus/response task.
- Barumerli et al. 2026 semantic looming is auditory looming-distance/motor-preparation PPS without a tactile stimulus/response task.
- Rossi Sebastiano et al. 2022 is visuo-tactile, not audio-tactile.
- Stone et al. 2017/2018 lower-limb PPS boundary work was a broad-screen false positive for this audit because the checked task is visuo-tactile, not audiotactile.
- Smartphone RT methods papers are useful implementation references, not published PPS task profiles.

## Standardization Priority

To generalize across the literature, the next toolkit schema work should prioritize:

1. Static near/far auditory trial families.
2. Richer baseline/catch families, including direction-coupled tactile-only baselines.
3. Audiovisual/trisensory trial-family metadata, so audio-tactile components embedded in audiovisual PPS tasks can be flagged honestly rather than silently approximated.
4. Response modes beyond mouse/button detection, especially voice-key and tactile discrimination/localization.
5. Audio renderer/source modes for multi-speaker arrays, Gaussian amplitude fields, HRTF provenance, and Unity/3D Tune-In equivalence notes; two-speaker analog setups should instead be extracted as reported trajectories and recreated binaurally when parameters are sufficient.
6. Body-relative and body-scaled coordinate systems.
7. Tactile modality/calibration metadata.
8. Tactile waveform/frequency profiles for haptic actuators.
9. Exact ITI/jitter, baseline-timing, repetition-count, and hazard-control policies when those timing policies define the PPS task.

Those additions, plus publication re-audits for exact missing parameters, are the main route toward making the toolkit a standardized capture system for the full audiotactile PPS task literature.

