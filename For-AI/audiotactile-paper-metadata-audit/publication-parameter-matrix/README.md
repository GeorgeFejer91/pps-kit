# Publication-to-Toolkit Input Review Matrix

Generated 2026-08-12 from the tracked `pps-publication-citation-network.v3` asset, exact-DOI audit joins, manual-review overrides, current profile manifests, and the repository's code/schema surfaces.

The primary paper-review deliverable is a **142-row × 13-contract categorical matrix** aligned to Toolkit Segments 1-5, runtime, pre-run study planning, and measurement acquisition: auditory stimulus; trajectory geometry plus kinematics; trial sequence; task/response behavior; jitter/ITI; SOA schedule; tactile target; baseline trials; catch trials; repetition allocation; block composition/order; study structure/schedule; and measurement acquisition/primary outcome. Every one of the 94 citation-network publications is represented, and a strict 94-row aggregate is supplied. The registered view has 142 rows because 29 publications have tracked multi-experiment or multi-profile splits.

The exact **142-row × 115-input** current design/profile matrices remain the implementation crosswalk. The broader **142-row × 281-leaf** target matrix remains a scientific-method and validation-gap inventory—not claims about fields accepted by the current serializer. Publications without a registry entry remain one review unit and are explicitly marked `experiment_count_not_assessed`; do not infer that they contain only one experiment. Only 37 of 94 nodes have tracked abstract text, and 26 have neither abstract text nor an exact-DOI audit record, so 142 is an evidence-backed review-row count rather than an exhaustive true experiment count.

The compact matrix reports whether contract-level evidence is complete, derived, partial, absent, unavailable, unassessed, or still composite. A reported or derived completion is component-gated: every required final component must have experiment-scoped evidence. The normalized evidence ledger preserves final component states, the underlying coarse-parent evidence, short paper value, source/page pointer, derivation note, exact current input paths, and any attached template encoding. It never promotes a coarse 25-field audit parent, template value, or Toolkit default to complete publication evidence. Controlled vocabularies distinguish generated/imported/physical sources, motion modes, timing policies, baseline trial families, catch target roles, exact versus unresolved allocation rules, study topology, assignment, factor scope/role, schedule events, outcome families, acquisition bindings, and synchronization methods. The 281-leaf atomic matrix remains stricter: each constituent target leaf still requires separate verification.

A registry state of `experiment_specific_source_review_available` authorizes only the dedicated experiment-scoped source-review override. It does not make a reused audit record or its record-level templates experiment-specific: coarse values remain composite in the atomic matrices, and templates are attached to child rows only when the registry names them explicitly.

The builder overwrites the named files recorded in
`generated_output_manifest.json`; it removes only obsolete files named by a
prior manifest and leaves unrelated files alone. Before entering manual values,
copy the review queue/sidecar to a dated working CSV and promote accepted
annotations into a durable reviewed-data source before rebuilding.

## Primary Parsimonious Paper-Review Files

- `study_instance_parsimonious_status_matrix.csv`: the primary compact have/missing table—142 registered study rows × 13 scientific emulation contracts.
- `study_instance_parsimonious_value_matrix.csv`: the same rows with short extracted paper values; composite-record evidence is visibly prefixed and never presented as experiment-specific.
- `publication_parsimonious_status_matrix.csv`: strict 94-publication aggregate; differing child rows become `mixed_across_studies`.
- `parsimonious_contract_evidence.csv`: normalized study × contract ledger with value, source/page, final and coarse component states, derivation, current-path crosswalk, and template encoding.
- `parsimonious_contract_review_queue.csv`: prioritized unresolved, caveated, and derived contract decisions.
- `parsimonious_contract_dictionary.csv`, `parsimonious_contract_summary.csv`, and `parsimonious_status_legend.csv`: contract definitions, coverage counts, and status meanings.
- `study_structure.csv`: one conservative structure-review row per registered study, including sample/assignment summaries, normalized topology, compiler-derived counts, provenance, and the explicit current Toolkit structural gap.
- `study_factor_levels.csv`: normalized factor/level rows with role, scope, assignment method, allocation rule, and optional planned/analyzed N per level.
- `study_schedule_events.csv`: normalized visit/session/PPS-occurrence schedule events with event links, factor bindings, execution mode, profile/protocol binding, and parameter overrides.
- `study_measurement_acquisitions.csv`: normalized dependent-measure/acquisition rows with outcome family, device/native binding, channels/sites, trigger/clock synchronization, acquisition window, primary outcome definition, and schedule/profile links. Analysis/model fitting is deliberately excluded.

Experiment-scoped values recovered from locally verified PDFs are stored as short tracked source reviews in `parsimonious_source_reviews.v1.json`; study-level topology/factor/event reviews use the separate versioned `study_structure_reviews.v1.json`, and dependent-measure/acquisition reviews use `measurement_acquisition_reviews.v1.json`, when present. Raw PDFs remain ignored and unredistributed.

The compact status matrix is intentionally categorical. Detailed values stay in the value matrix and evidence ledger so the paper-facing sheet remains small. Geometry and kinematics are one reconstructibility contract: a canonical 3D/body-relative path plus enough of duration, path length, and speed to derive the redundant quantity. Baseline and catch remain separate because a tactile-only or endpoint control is not equivalent to a no-target/withhold trial, and auditory-only response trials must not be mislabeled as catches. EEG/prestimulus analysis baselines are excluded from the trial-generation baseline contract. Study structure is one contract in the wide matrix but normalizes into parent/factor/event child tables; its destination is a future pre-run `pps-study-plan.v1` artifact, not Segment 6 and not the current design serializer. Existing dashboard/run-setup dictionaries are retained only as legacy untyped metadata and do not count as implementation support. Measurement acquisition is a separate dependency-gated contract so EEG/iEEG/TMS-MEP/ECG/physiology studies cannot appear reproducible from stimulus and RT settings alone. Behavioral-only studies can bind to the native response log and reference `task_response` without repeating response mechanics. Current LSL/LabRecorder support is runtime scaffolding, not a typed device/channel/epoch/outcome plan; the future destination is an acquisition binding from `pps-study-plan.v1` to `pps-acquisition-plan.v1`. Offline analysis and model fitting remain outside this input matrix.

## Current-Toolkit Implementation Crosswalk Files

- `study_instance_current_input_review_matrix.csv`: implementation-level evidence table—142 registered study/profile rows × 115 exact current serialized input columns.
- `publication_current_input_review_matrix.csv`: the same evidence-review states aggregated to the 94 citation-network publications.
- `current_input_review_queue.csv`: normalized long manual-review queue for all 16330 current-input cells, including composite-evidence and untyped-object warnings.
- `current_input_to_target_crosswalk.csv`: inverse mapping from every exact current input to the proposed target leaves and coarse audit parents used to seed its review status.
- `current_input_review_status_legend.csv`: interpretation and required action for every current-evidence review category.
- `study_instance_current_toolkit_input_matrix.csv`: 142 registered study rows × 115 exact inputs accepted by `design_from_dict` and emitted by `design_to_dict`.
- `publication_current_toolkit_input_matrix.csv`: the same current input paths aggregated to the 94 publication nodes.
- `current_toolkit_input_dictionary.csv`: code-derived path, type, default, cardinality, parser, serializer, and source-line contract for every current input.
- `current_toolkit_input_values.csv`: normalized experiment/variant-scoped profile values by study, profile, and exact input path.
- `publication_current_toolkit_input_values.csv`: publication-scoped profile values, including composite profiles that are intentionally not assigned to individual experiment rows.
- `current_toolkit_input_status_legend.csv`: categorical encoding states used in the current matrices.

These implementation matrices describe the exact current **design/profile serialization** surface and what attached templates encode. They are not an inventory of every operational Toolkit namespace: capture, loudness, tactile calibration, adaptive tactile, top-up, latency validation, and analysis policies remain separately listed in `implementation_surface_inventory.csv`. They also do not by themselves prove that a value was reported by, or faithfully reconstructed from, a publication. Check `publication_profile_scope`: a `composite_profile_not_experiment_scoped` profile is visible only in the publication aggregate until its values are disaggregated.

## Secondary Target Method/Validation-Gap Files

- `study_instance_target_method_validation_gap_matrix.csv`: secondary 142-row scientific method/validation inventory; multi-experiment papers are labeled `(a)`, `(b)`, `(c)`, and so on.
- `publication_target_method_validation_gap_matrix.csv`: strict 94-node target aggregate; `mixed` points back to differing study-instance rows.
- `target_method_validation_dictionary.csv`: all 281 proposed target method/validation paths, shapes, units, roles, repeating entities, coarse audit-parent mappings, and exact current-design crosswalk fields. Six leaves are explicitly validation/derived candidates rather than configuration inputs; older routing hints remain provisional.
- `target_method_to_current_input_crosswalk.csv`: conservative mapping from every proposed target leaf to exact current `design.*` paths, an untyped object container, a partial proxy/derived value, or `not_in_current_design_serializer`.
- `study_instance_target_method_review_queue.csv`: editable long target-review queue for every study/target pair, priority-sorted.
- `study_instance_target_method_evidence_sidecar.csv`: normalized target evidence/status ledger keyed by `(study_row_id, target_parameter_path)`.
- `target_method_validation_parameter_summary.csv` and `target_method_validation_group_summary.csv`: recovery load by proposed leaf/group.
- `study_orientation_review.csv`: one row per study instance with current structured orientation ledgers and empty visual-orientation verification fields.
- `study_visualizations.csv`: normalized one-to-many figure/table/panel review table; automated candidates are explicitly unconfirmed.
- `target_method_validation_status_legend.csv`: atomic-review, binding, and provisional routing-hint taxonomies.

## Supporting Files

- `generated_output_manifest.json`: exact managed file set for reproducibility and stale-artifact detection.
- `study_instance_index.csv` and `publication_study_index.csv`: human-readable row/publication metadata and exact joins.
- `publication_parameter_matrix.csv`: the current coarse 25-field publication audit plus 19 profile inventory fields and 7 generic gap fields. It is retained only as a migration baseline.
- `publication_parameter_evidence_detail.csv`, `publication_parameter_dictionary.csv`, `publication_parameter_summary.csv`, `publication_parameter_review_queue.csv`, and `publication_parameter_status_legend.csv`: current-schema evidence and gate diagnostics.
- `implementation_surface_inventory.csv`: separates current design inputs, other runtime/calibration namespaces, target leaves, and output-only schemas.
- `implementation_discrepancies.csv`: code/schema/documentation mismatches found during the inventory.
- `audit_records_outside_network.csv`: six audit records intentionally not joined to the focused 94-node display.

## Snapshot

| Measure | Count |
|---|---:|
| Focused publication nodes | 94 |
| Citation links | 750 |
| Evidence-backed registered study/profile rows | 142 |
| Parsimonious paper-facing contract columns | 13 |
| Parsimonious study-contract evidence cells | 1846 |
| Exact current serialized Toolkit input columns | 115 |
| Current-input categorical review cells | 16330 |
| Proposed target method/validation columns | 281 |
| Target-review categorical cells | 39902 |
| Target leaves mapped to a current coarse audit parent | 220 |
| Target leaves absent from the current 25-field audit | 61 |
| Exact current paths absent from the proposed target inventory | 26 |
| Exact-DOI joined audit records | 69 |
| Publication nodes without an audit record | 29 |
| Publication nodes with tracked abstract text | 37 |
| Publication nodes with neither abstract text nor an audit record | 26 |
| Manual-review records joined to nodes | 24 |
| Manual-review records with structured orientation ledgers | 7 |
| Experiment-specific rows with a directly scoped orientation ledger | 3 |
| Split rows inheriting a combined-record orientation ledger | 10 |
| Automated visualization candidates needing visual verification | 173 |
| Study-level visualization candidate rows after experiment splitting | 276 |
| Confirmed structured visualization rows | 0 |
| Audit records outside focused network | 6 |

Toolkit publication states: `adjacent_scope_conflict` 1, `not_assessed` 29, `runnable` 15, `supported_incomplete` 49.

Study-instance evidence stages: `current_audit_without_manual_review` 68, `manual_review` 35, `no_exact_doi_audit_join` 39.

## Multi-Experiment Publication Labels

| Publication | Study rows | Record/template identities |
|---|---:|---|
| Auditory peripersonal space in humans. | 2 | doi:10.1162/089892902320474481::a \| doi:10.1162/089892902320474481::b |
| Dynamic sounds capture the boundaries of peripersonal space representation in humans. | 2 | doi:10.1371/journal.pone.0044306::a \| doi:10.1371/journal.pone.0044306::b |
| Social modulation of peripersonal space boundaries. | 3 | doi:10.1016/j.cub.2013.01.043::a \| doi:10.1016/j.cub.2013.01.043::b \| doi:10.1016/j.cub.2013.01.043::c |
| Body part-centered and full body-centered peripersonal space representations. | 7 | doi:10.1038/srep18603::a \| doi:10.1038/srep18603::b \| doi:10.1038/srep18603::c \| doi:10.1038/srep18603::d \| doi:10.1038/srep18603::e \| doi:10.1038/srep18603::f \| doi:10.1038/srep18603::g |
| Everyday use of the computer mouse extends peripersonal space representation. | 2 | doi:10.1016/j.neuropsychologia.2009.11.009::a \| doi:10.1016/j.neuropsychologia.2009.11.009::b |
| Tool-use reshapes the boundaries of body and peripersonal space representations. | 2 | doi:10.1007/s00221-013-3532-2::a \| doi:10.1007/s00221-013-3532-2::b |
| Full body action remapping of peripersonal space: the case of walking. | 2 | doi:10.1016/j.neuropsychologia.2014.08.030::a \| doi:10.1016/j.neuropsychologia.2014.08.030::b |
| Fronto-parietal areas necessary for a multisensory representation of peripersonal space in humans: an rTMS study. | 3 | doi:10.1162/jocn_a_00006::a \| doi:10.1162/jocn_a_00006::b \| doi:10.1162/jocn_a_00006::c |
| Peripersonal space as the space of the bodily self. | 3 | doi:10.1016/j.cognition.2015.07.012::a \| doi:10.1016/j.cognition.2015.07.012::b \| doi:10.1016/j.cognition.2015.07.012::c |
| Emotion-inducing approaching sounds shape the boundaries of multisensory peripersonal space. | 2 | doi:10.1016/j.neuropsychologia.2015.03.001::a \| doi:10.1016/j.neuropsychologia.2015.03.001::b |
| Amputation and prosthesis implantation shape body and peripersonal space representations. | 3 | doi:10.1038/srep02844::a \| doi:10.1038/srep02844::b \| doi:10.1038/srep02844::c |
| Motor properties of peripersonal space in humans. | 2 | doi:10.1371/journal.pone.0006582::a \| doi:10.1371/journal.pone.0006582::b |
| Extending peripersonal space representation without tool-use: evidence from a combined behavioral-computational approach. | 2 | doi:10.3389/fnbeh.2015.00004::a \| doi:10.3389/fnbeh.2015.00004::b |
| The wheelchair as a full-body tool extending the peripersonal space. | 3 | doi:10.3389/fpsyg.2015.00639::a \| doi:10.3389/fpsyg.2015.00639::b \| doi:10.3389/fpsyg.2015.00639::c |
| Peripersonal Space: An Index of Multisensory Body–Environment Interactions in Real, Virtual, and Mixed Realities | 2 | doi:10.3389/fict.2017.00031::a \| doi:10.3389/fict.2017.00031::b |
| Vestibular modulation of peripersonal space boundaries. | 3 | doi:10.1111/ejn.13872::a \| doi:10.1111/ejn.13872::b \| doi:10.1111/ejn.13872::c |
| Do sounds near the hand facilitate tactile reaction times? Four experiments and a meta-analysis provide mixed support and suggest a small effect size. | 4 | doi:10.1007/s00221-020-05771-5::a \| doi:10.1007/s00221-020-05771-5::b \| doi:10.1007/s00221-020-05771-5::c \| doi:10.1007/s00221-020-05771-5::d |
| Social coding of the multisensory space around us. | 3 | doi:10.1098/rsos.181878::a \| doi:10.1098/rsos.181878::b \| doi:10.1098/rsos.181878::c |
| Seeing the body modulates audiotactile integration | 3 | doi:10.1111/j.1460-9568.2010.07210.x::a \| doi:10.1111/j.1460-9568.2010.07210.x::b \| doi:10.1111/j.1460-9568.2010.07210.x::c |
| Identifying peripersonal space boundaries in newborns. | 2 | doi:10.1038/s41598-019-45084-4::a \| doi:10.1038/s41598-019-45084-4::b |
| Multisensory integration in Peripersonal Space indexes consciousness states in sleep and disorders of consciousness | 2 | doi:10.1101/2024.10.25.619776::a \| doi:10.1101/2024.10.25.619776::b |
| Social impact on audiotactile integration near the body | 3 | doi:10.1250/ast.41.345::a \| doi:10.1250/ast.41.345::b \| doi:10.1250/ast.41.345::c |
| Peri-personal space encoding in patients with disorders of consciousness and cognitive-motor dissociation. | 2 | doi:10.1016/j.nicl.2019.101940::a \| doi:10.1016/j.nicl.2019.101940::b |
| Dealing with the world close to our body. Characterizing determinants of peripersonal space plasticity. | 4 | doi:10.1016/j.neuropsychologia.2026.109490::a \| doi:10.1016/j.neuropsychologia.2026.109490::b \| doi:10.1016/j.neuropsychologia.2026.109490::c \| doi:10.1016/j.neuropsychologia.2026.109490::d |
| Multisensory integration in peripersonal space indexes consciousness states in sleep and disorders of consciousness. | 2 | doi:10.1016/j.xcrm.2026.102705::a \| doi:10.1016/j.xcrm.2026.102705::b |
| Somatotopy-independent reduction of audio-tactile intersensory facilitation for looming sounds within the peripersonal space during arm movements execution. | 2 | doi:10.1038/s41598-026-36796-5::a \| doi:10.1038/s41598-026-36796-5::b |
| The spatial reach of affective touch: a new perspective on social peripersonal space | 3 | doi:10.31234/osf.io/etvb6_v1::a \| doi:10.31234/osf.io/etvb6_v1::b \| doi:10.31234/osf.io/etvb6_v1::c |
| Using Android Smartphones to Collect Precise Measures of Reaction Times to Multisensory Stimuli. | 2 | doi:10.3390/s25196072::a \| doi:10.3390/s25196072::b |
| The Impact of Looming Sound Duration on Peripersonal Space Measurement | 2 | doi:10.61782/fa.2025.0866::a \| doi:10.61782/fa.2025.0866::b |

The suffix letters are review/display labels. Existing `record_id` and `profile_id` values are preserved unchanged.

## Proposed Target Method/Validation Groups

| Group | Namespace | Leaves | Coarse-parent mapped | New audit leaves | Structural gaps |
|---|---|---:|---:|---:|---:|
| Study and profile design | `0` | 17 | 0 | 17 | 1 |
| Auditory and source definition | `1` | 29 | 29 | 0 | 0 |
| Trajectory and orientation | `1` | 33 | 33 | 0 | 2 |
| Renderer, loudness, visual, and mixed-reality context | `1` | 49 | 49 | 0 | 12 |
| Trial sequence and task | `2` | 26 | 26 | 0 | 0 |
| Tactile, SOA, baseline, and catch | `3` | 39 | 39 | 0 | 0 |
| Repetition and trial counts | `4` | 18 | 18 | 0 | 0 |
| Block design | `5` | 14 | 7 | 7 | 0 |
| Profile finalization, instructions, and order | `6` | 14 | 0 | 14 | 0 |
| Runtime task, response, and hardware | `runtime` | 23 | 19 | 4 | 0 |
| Analysis policy and PPS visualization | `analysis` | 19 | 0 | 19 | 0 |

## Atomic Review Status Totals

| Status | Cells |
|---|---:|
| `composite_parent_atomic_unreviewed` | 12760 |
| `not_assessed` | 8580 |
| `not_covered_by_current_audit` | 8662 |
| `parent_derived_atomic_unreviewed` | 114 |
| `parent_low_confidence_atomic_unreviewed` | 1191 |
| `parent_not_applicable_atomic_unreviewed` | 273 |
| `parent_reported_atomic_unreviewed` | 2931 |
| `parent_reviewed_missing` | 196 |
| `source_unavailable` | 5195 |

These totals distinguish four different kinds of unresolved work: no audit at all, unavailable/unextracted source evidence, a reviewed-but-missing coarse parent, and a brand-new atomic input not covered by the current audit.

## Largest Atomic Recovery Loads

| Proposed target method/validation leaf | Group | Reviewed-parent missing | Source unknown | Not in current audit | Provisional routing hint |
|---|---|---:|---:|---:|---|
| `target.runtime.online_timeout_ms` | Runtime task, response, and hardware | 10 | 64 | 0 | `runtime_only` |
| `target.runtime.response_window_anchor` | Runtime task, response, and hardware | 10 | 64 | 0 | `runtime_only` |
| `target.runtime.response_window_max_ms` | Runtime task, response, and hardware | 10 | 64 | 0 | `runtime_only` |
| `target.runtime.response_window_min_ms` | Runtime task, response, and hardware | 10 | 64 | 0 | `runtime_only` |
| `target.block_design.block_count` | Block design | 4 | 67 | 0 | `first_class_gui` |
| `target.trial_sequence.foreperiod_ms` | Trial sequence and task | 4 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.iti_distribution` | Trial sequence and task | 4 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.iti_policy` | Trial sequence and task | 4 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.iti_values_or_range_ms` | Trial sequence and task | 4 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.jitter_randomized` | Trial sequence and task | 4 | 63 | 0 | `first_class_gui` |
| `target.trial_sequence.jitter_values_ms` | Trial sequence and task | 4 | 63 | 0 | `first_class_gui` |
| `target.trial_sequence.post_sound_silence_ms` | Trial sequence and task | 4 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.pre_sound_silence_ms` | Trial sequence and task | 4 | 63 | 0 | `backend_schema_only` |
| `target.block_design.block_order_randomization` | Block design | 4 | 62 | 0 | `first_class_gui` |
| `target.block_design.condition_blocking_or_intermixing` | Block design | 4 | 62 | 0 | `first_class_gui` |

## Provisional Target Routing Hints

| Routing hint | Target method/validation leaves |
|---|---:|
| `analysis_only` | 19 |
| `backend_schema_only` | 95 |
| `derived_materialized` | 6 |
| `first_class_gui` | 85 |
| `fixed_policy_not_configurable` | 1 |
| `freeform_metadata_only` | 37 |
| `runtime_only` | 23 |
| `unsupported_structural_gap` | 15 |

The 15 explicitly identified structural gaps are:

- `target.study.planned_sample_n`
- `target.trajectories.elevation_start_deg`
- `target.trajectories.elevation_end_deg`
- `target.rendering.speaker_switch_sequence`
- `target.rendering.speaker_switch_times_ms`
- `target.rendering.speaker_switch_channels`
- `target.rendering.speaker_switch_gains`
- `target.rendering.speaker_source_channel`
- `target.rendering.visual_start_distance_cm`
- `target.rendering.visual_end_distance_cm`
- `target.rendering.visual_speed_cm_s`
- `target.rendering.visual_duration_ms`
- `target.rendering.visual_renderer_engine`
- `target.rendering.audiovisual_synchrony_policy`
- `target.rendering.mixed_reality_equivalence_boundary`

These legacy hints are only triage labels. They are not evidence that a target leaf is accepted, serialized, GUI-bound, or consumed by the current Toolkit; use the exact current-input dictionary and target crosswalk for implementation claims.

## Exact Current-Design Crosswalk

| Binding state | Proposed target leaves |
|---|---:|
| `composite_over_typed_current_inputs` | 5 |
| `derived_not_input` | 7 |
| `not_in_current_design_serializer` | 86 |
| `partial_or_proxy_current_input` | 25 |
| `typed_current_input` | 48 |
| `untyped_object_container_only` | 110 |

This crosswalk is intentionally scoped to `StimulusDesign` serialization. Runtime, calibration, and analysis contracts remain in the implementation-surface inventory unless they have a versioned profile binding; absence from this crosswalk does not prove the concept is absent from every code path.

The proposed target inventory is also not a superset of the current serializer. These 26 exact current paths have no target relation and therefore remain visible as `not_covered_by_target_inventory` in the primary current-input review matrix:

- `design.name`
- `design.study_profile_id`
- `design.study_profile_title`
- `design.study_profile_notes`
- `design.noises[].azimuth_deg`
- `design.noises[].elevation_deg`
- `design.noises[].prebaked_path`
- `design.noises[].sequence_order`
- `design.custom_looming_files[].path`
- `design.custom_looming_files[].placement`
- `design.custom_looming_files[].target_source_label`
- `design.custom_looming_files[].phase`
- `design.custom_looming_files[].gap_s`
- `design.custom_looming_files[].sequence_order`
- `design.custom_looming_files[].display_color_hex`
- `design.custom_looming_files[].source_input_path`
- `design.prestimulus_files[].path`
- `design.prestimulus_files[].placement`
- `design.prestimulus_files[].target_source_label`
- `design.prestimulus_files[].phase`
- `design.prestimulus_files[].gap_s`
- `design.prestimulus_files[].sequence_order`
- `design.prestimulus_files[].display_color_hex`
- `design.prestimulus_files[].source_input_path`
- `design.protocol.auditory_motion_directions`
- `design.protocol.respiratory_phases`

## Systematic Review Gaps

- Only 7 of 24 manual-review records contain the current structured orientation ledger. Of the registered rows, 3 have an experiment-scoped ledger and 10 inherit a combined-record ledger that still needs experiment-specific checking. The orientation worksheet therefore keeps participant frame, apparatus frame, body-relative mapping, tactile anchor, movement implementation, evidence class, and visual-vector verification separate.
- There are 173 automated visualization candidates in joined studies and **zero confirmed structured figure reviews**. Every candidate must be checked against the rendered figure/table/panel, axes, units, model, boundary/index definition, facets, and uncertainty display.
- 61 proposed target method/validation leaves have no parent in the current 25-field extraction schema; these are not paper absences, just audit-schema gaps.
- `source_unavailable` is overloaded in automated records: it can mean no candidate was mined from an available source, not necessarily that the publication itself is unavailable. Use PDF, extraction, and manual-review stage columns together.

## Current Coarse Fields With The Largest Review Load

| Parent field | Segment | Actionable publications | Leading action |
|---|---:|---:|---|
| `PUB.S2.response_window` | 2 | 84 | `acquire_or_open_source` |
| `PUB.S4.total_trial_count` | 4 | 83 | `acquire_or_open_source` |
| `PUB.S1.gain_envelope` | 1 | 79 | `acquire_or_open_source` |
| `PUB.S2.iti_jitter_policy` | 2 | 79 | `acquire_or_open_source` |
| `PUB.S1.source_provenance` | 1 | 77 | `acquire_or_open_source` |
| `PUB.S4.baseline_count` | 4 | 77 | `acquire_or_open_source` |
| `PUB.S4.catch_count` | 4 | 77 | `acquire_or_open_source` |
| `PUB.S1.stimulus_speed` | 1 | 76 | `acquire_or_open_source` |
| `PUB.S1.stimulus_type` | 1 | 74 | `acquire_or_open_source` |
| `PUB.S3.soa_table` | 3 | 74 | `acquire_or_open_source` |

## Review Rules

1. Enter source values only in the long review/evidence ledger, keyed by `study_row_id` and proposed target parameter path. Keep the wide matrix categorical.
2. Never collapse `not_assessed`, `source_unavailable`, `parent_reviewed_missing`, and `not_covered_by_current_audit` into one blank.
3. Manual reviews override automated candidates. Never propagate values between related preprint/final-version DOIs without explicit version lineage.
4. Follow the retrieval ladder before closing a leaf as missing: main paper, figures/tables, supplement, publisher/fallback source, cited protocol lineage, then arithmetic/coordinate consistency.
5. For repeatable sources, trajectories, rows, blocks, parts, and instructions, store arrays/objects under the one target leaf rather than creating ad hoc columns.
6. A Toolkit support state is not evidence quality. Citation prominence is used only to order review work and is not a study-quality rating.
