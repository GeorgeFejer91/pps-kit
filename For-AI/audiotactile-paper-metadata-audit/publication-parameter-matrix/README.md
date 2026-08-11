# Publication-to-Toolkit Input Review Matrix

Generated 2026-08-11 from the tracked `pps-publication-citation-network.v3` asset, exact-DOI audit joins, manual-review overrides, current profile manifests, and the repository's code/schema surfaces.

The primary requested deliverable is a **121-row × 111-column categorical review matrix** whose columns are exact current serialized design/profile inputs. Every one of the 94 citation-network publications is represented, and a strict 94-row aggregate is supplied. The registered view has 121 rows because 14 publications have tracked multi-experiment or multi-profile splits.

The secondary **121-row × 281-column** matrix is a proposed scientific-method and validation-gap inventory—not claims about fields accepted by the current serializer and not a superset of every current identity/operational input. Publications without a registry entry remain one review unit and are explicitly marked `experiment_count_not_assessed`; do not infer that they contain only one experiment. Only 37 of 94 nodes have tracked abstract text, and 26 have neither abstract text nor an exact-DOI audit record, so 121 is an evidence-backed review-row count rather than an exhaustive true experiment count.

Every atomic cell currently remains a review task. Existing reviews were performed against 25 coarse parent fields, so even a reported parent is labeled `parent_reported_atomic_unreviewed` until its constituent target method/validation leaves are separately verified. Values/evidence live in normalized side tables; categorical status stays in the wide matrices.

The builder overwrites the named files recorded in
`generated_output_manifest.json`; it removes only obsolete files named by a
prior manifest and leaves unrelated files alone. Before entering manual values,
copy the review queue/sidecar to a dated working CSV and promote accepted
annotations into a durable reviewed-data source before rebuilding.

## Primary Current-Toolkit Files

- `study_instance_current_input_review_matrix.csv`: the requested categorical review table—121 registered study/profile rows × 111 exact current serialized input columns.
- `publication_current_input_review_matrix.csv`: the same evidence-review states aggregated to the 94 citation-network publications.
- `current_input_review_queue.csv`: normalized long manual-review queue for all 13431 current-input cells, including composite-evidence and untyped-object warnings.
- `current_input_to_target_crosswalk.csv`: inverse mapping from every exact current input to the proposed target leaves and coarse audit parents used to seed its review status.
- `current_input_review_status_legend.csv`: interpretation and required action for every current-evidence review category.
- `study_instance_current_toolkit_input_matrix.csv`: 121 registered study rows × 111 exact inputs accepted by `design_from_dict` and emitted by `design_to_dict`.
- `publication_current_toolkit_input_matrix.csv`: the same current input paths aggregated to the 94 publication nodes.
- `current_toolkit_input_dictionary.csv`: code-derived path, type, default, cardinality, parser, serializer, and source-line contract for every current input.
- `current_toolkit_input_values.csv`: normalized experiment/variant-scoped profile values by study, profile, and exact input path.
- `publication_current_toolkit_input_values.csv`: publication-scoped profile values, including composite profiles that are intentionally not assigned to individual experiment rows.
- `current_toolkit_input_status_legend.csv`: categorical encoding states used in the current matrices.

The primary matrices describe the exact current **design/profile serialization** surface and what attached templates encode. They are not an inventory of every operational Toolkit namespace: capture, loudness, tactile calibration, adaptive tactile, top-up, latency validation, and analysis policies remain separately listed in `implementation_surface_inventory.csv`. They also do not by themselves prove that a value was reported by, or faithfully reconstructed from, a publication. Check `publication_profile_scope`: a `composite_profile_not_experiment_scoped` profile is visible only in the publication aggregate until its values are disaggregated.

## Secondary Target Method/Validation-Gap Files

- `study_instance_target_method_validation_gap_matrix.csv`: secondary 121-row scientific method/validation inventory; multi-experiment papers are labeled `(a)`, `(b)`, `(c)`, and so on.
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
| Evidence-backed registered study/profile rows | 121 |
| Exact current serialized Toolkit input columns | 111 |
| Current-input categorical review cells | 13431 |
| Proposed target method/validation columns | 281 |
| Target-review categorical cells | 34001 |
| Target leaves mapped to a current coarse audit parent | 220 |
| Target leaves absent from the current 25-field audit | 61 |
| Exact current paths absent from the proposed target inventory | 22 |
| Exact-DOI joined audit records | 69 |
| Publication nodes without an audit record | 29 |
| Publication nodes with tracked abstract text | 37 |
| Publication nodes with neither abstract text nor an audit record | 26 |
| Manual-review records joined to nodes | 24 |
| Manual-review records with structured orientation ledgers | 7 |
| Experiment-specific rows with a directly scoped orientation ledger | 4 |
| Split rows inheriting a combined-record orientation ledger | 8 |
| Automated visualization candidates needing visual verification | 173 |
| Study-level visualization candidate rows after experiment splitting | 247 |
| Confirmed structured visualization rows | 0 |
| Audit records outside focused network | 6 |

Toolkit publication states: `adjacent_scope_conflict` 1, `not_assessed` 29, `runnable` 15, `supported_incomplete` 49.

Study-instance evidence stages: `current_audit_without_manual_review` 55, `manual_review` 34, `no_exact_doi_audit_join` 32.

## Multi-Experiment Publication Labels

| Publication | Study rows | Record/template identities |
|---|---:|---|
| Auditory peripersonal space in humans. | 2 | doi:10.1162/089892902320474481::a \| doi:10.1162/089892902320474481::b |
| Body part-centered and full body-centered peripersonal space representations. | 7 | doi:10.1038/srep18603::a \| doi:10.1038/srep18603::b \| doi:10.1038/srep18603::c \| doi:10.1038/srep18603::d \| doi:10.1038/srep18603::e \| doi:10.1038/srep18603::f \| doi:10.1038/srep18603::g |
| Full body action remapping of peripersonal space: the case of walking. | 2 | doi:10.1016/j.neuropsychologia.2014.08.030::a \| doi:10.1016/j.neuropsychologia.2014.08.030::b |
| Peripersonal space as the space of the bodily self. | 3 | doi:10.1016/j.cognition.2015.07.012::a \| doi:10.1016/j.cognition.2015.07.012::b \| doi:10.1016/j.cognition.2015.07.012::c |
| Emotion-inducing approaching sounds shape the boundaries of multisensory peripersonal space. | 2 | doi:10.1016/j.neuropsychologia.2015.03.001::a \| doi:10.1016/j.neuropsychologia.2015.03.001::b |
| Amputation and prosthesis implantation shape body and peripersonal space representations. | 3 | doi:10.1038/srep02844::a \| doi:10.1038/srep02844::b \| doi:10.1038/srep02844::c |
| The wheelchair as a full-body tool extending the peripersonal space. | 3 | doi:10.3389/fpsyg.2015.00639::a \| doi:10.3389/fpsyg.2015.00639::b \| doi:10.3389/fpsyg.2015.00639::c |
| Peripersonal Space: An Index of Multisensory Body–Environment Interactions in Real, Virtual, and Mixed Realities | 2 | doi:10.3389/fict.2017.00031::a \| doi:10.3389/fict.2017.00031::b |
| Vestibular modulation of peripersonal space boundaries. | 3 | doi:10.1111/ejn.13872::a \| doi:10.1111/ejn.13872::b \| doi:10.1111/ejn.13872::c |
| Do sounds near the hand facilitate tactile reaction times? Four experiments and a meta-analysis provide mixed support and suggest a small effect size. | 4 | doi:10.1007/s00221-020-05771-5::a \| doi:10.1007/s00221-020-05771-5::b \| doi:10.1007/s00221-020-05771-5::c \| doi:10.1007/s00221-020-05771-5::d |
| Peri-personal space encoding in patients with disorders of consciousness and cognitive-motor dissociation. | 2 | doi:10.1016/j.nicl.2019.101940::a \| doi:10.1016/j.nicl.2019.101940::b |
| Dealing with the world close to our body. Characterizing determinants of peripersonal space plasticity. | 4 | doi:10.1016/j.neuropsychologia.2026.109490::a \| doi:10.1016/j.neuropsychologia.2026.109490::b \| doi:10.1016/j.neuropsychologia.2026.109490::c \| doi:10.1016/j.neuropsychologia.2026.109490::d |
| Multisensory integration in peripersonal space indexes consciousness states in sleep and disorders of consciousness. | 2 | doi:10.1016/j.xcrm.2026.102705::a \| doi:10.1016/j.xcrm.2026.102705::b |
| Somatotopy-independent reduction of audio-tactile intersensory facilitation for looming sounds within the peripersonal space during arm movements execution. | 2 | doi:10.1038/s41598-026-36796-5::a \| doi:10.1038/s41598-026-36796-5::b |

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
| `composite_parent_atomic_unreviewed` | 7260 |
| `not_assessed` | 7040 |
| `not_covered_by_current_audit` | 7381 |
| `parent_caveated_atomic_unreviewed` | 9 |
| `parent_derived_atomic_unreviewed` | 129 |
| `parent_lineage_derived_atomic_unreviewed` | 7 |
| `parent_low_confidence_atomic_unreviewed` | 1584 |
| `parent_not_applicable_atomic_unreviewed` | 277 |
| `parent_reported_absent_atomic_unreviewed` | 6 |
| `parent_reported_atomic_unreviewed` | 3302 |
| `parent_reviewed_missing` | 224 |
| `source_unavailable` | 6782 |

These totals distinguish four different kinds of unresolved work: no audit at all, unavailable/unextracted source evidence, a reviewed-but-missing coarse parent, and a brand-new atomic input not covered by the current audit.

## Largest Atomic Recovery Loads

| Proposed target method/validation leaf | Group | Reviewed-parent missing | Source unknown | Not in current audit | Provisional routing hint |
|---|---|---:|---:|---:|---|
| `target.runtime.online_timeout_ms` | Runtime task, response, and hardware | 11 | 65 | 0 | `runtime_only` |
| `target.runtime.response_window_anchor` | Runtime task, response, and hardware | 11 | 65 | 0 | `runtime_only` |
| `target.runtime.response_window_max_ms` | Runtime task, response, and hardware | 11 | 65 | 0 | `runtime_only` |
| `target.runtime.response_window_min_ms` | Runtime task, response, and hardware | 11 | 65 | 0 | `runtime_only` |
| `target.trial_sequence.foreperiod_ms` | Trial sequence and task | 5 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.iti_distribution` | Trial sequence and task | 5 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.iti_policy` | Trial sequence and task | 5 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.iti_values_or_range_ms` | Trial sequence and task | 5 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.jitter_randomized` | Trial sequence and task | 5 | 63 | 0 | `first_class_gui` |
| `target.trial_sequence.jitter_values_ms` | Trial sequence and task | 5 | 63 | 0 | `first_class_gui` |
| `target.trial_sequence.post_sound_silence_ms` | Trial sequence and task | 5 | 63 | 0 | `backend_schema_only` |
| `target.trial_sequence.pre_sound_silence_ms` | Trial sequence and task | 5 | 63 | 0 | `backend_schema_only` |
| `target.block_design.block_count` | Block design | 4 | 69 | 0 | `first_class_gui` |
| `target.rendering.distance_gain_policy` | Renderer, loudness, visual, and mixed-reality context | 4 | 66 | 0 | `backend_schema_only` |
| `target.rendering.end_spl_db` | Renderer, loudness, visual, and mixed-reality context | 4 | 66 | 0 | `first_class_gui` |

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

The proposed target inventory is also not a superset of the current serializer. These 22 exact current paths have no target relation and therefore remain visible as `not_covered_by_target_inventory` in the primary current-input review matrix:

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
- `design.prestimulus_files[].path`
- `design.prestimulus_files[].placement`
- `design.prestimulus_files[].target_source_label`
- `design.prestimulus_files[].phase`
- `design.prestimulus_files[].gap_s`
- `design.prestimulus_files[].sequence_order`
- `design.protocol.auditory_motion_directions`
- `design.protocol.respiratory_phases`

## Systematic Review Gaps

- Only 7 of 24 manual-review records contain the current structured orientation ledger. Of the registered rows, 4 have an experiment-scoped ledger and 8 inherit a combined-record ledger that still needs experiment-specific checking. The orientation worksheet therefore keeps participant frame, apparatus frame, body-relative mapping, tactile anchor, movement implementation, evidence class, and visual-vector verification separate.
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
