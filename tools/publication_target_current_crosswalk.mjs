/**
 * Conservative crosswalk from proposed scientific target leaves to the exact
 * current StimulusDesign serializer contract.
 *
 * A mapping is not evidence that a publication value is correct.  It says only
 * how (or whether) a target concept can enter design_from_dict/design_to_dict
 * today.  Arbitrary dict containers are deliberately labelled untyped.
 */

const P = {
  reference: "design.study_profile_reference_parameters",
  sourceProfile: "design.noises[].source_profile_parameters",
  noiseSnapshot: "design.noises[].trajectory_snapshot",
  customSnapshot: "design.custom_looming_files[].trajectory_snapshot",
  prestimulusSnapshot: "design.prestimulus_files[].trajectory_snapshot",
  rowMetadata: "design.protocol.trial_strips[].metadata",
  participantOrder: "design.protocol.participant_order_policy",
};

const binding = (state, paths, basis) => ({ state, paths, basis });
const typed = (paths, basis = "explicit semantic crosswalk") =>
  binding("typed_current_input", paths, basis);
const transformed = (paths, basis) =>
  binding("typed_current_input_with_transform", paths, basis);
const composite = (paths, basis) =>
  binding("composite_over_typed_current_inputs", paths, basis);
const proxy = (paths, basis) =>
  binding("partial_or_proxy_current_input", paths, basis);
const derived = (paths, basis) => binding("derived_not_input", paths, basis);
const untyped = (paths, basis) => binding("untyped_object_container_only", paths, basis);

const sourceLabels = [
  "design.noises[].label",
  "design.custom_looming_files[].label",
  "design.prestimulus_files[].label",
];
const sourceGains = [
  "design.noises[].gain",
  "design.custom_looming_files[].gain",
  "design.prestimulus_files[].gain",
];
const sourceMotionModes = [
  "design.noises[].motion_mode",
  "design.custom_looming_files[].motion_mode",
  "design.prestimulus_files[].motion_mode",
];
const sourceSnapshots = [P.noiseSnapshot, P.customSnapshot, P.prestimulusSnapshot];

const EXPLICIT = new Map([
  ["target.sources.source_count", derived(sourceLabels, "count of instantiated source entities; not a serialized scalar")],
  ["target.sources.source_labels", composite(sourceLabels, "labels are typed separately for each current source collection")],
  ["target.sources.source_kind", proxy(["design.noises[].noise_type", "design.custom_looming_files[].render_mode", "design.prestimulus_files[].render_mode"], "source collection and subtype fields jointly encode kind")],
  ["target.sources.auditory_stimulus_type", proxy(["design.noises[].noise_type", "design.custom_looming_files[].tone_type", "design.prestimulus_files[].tone_type"], "current typed subtypes cover only part of the target concept")],
  ["target.sources.auditory_condition_labels", composite(sourceLabels, "current source labels are the nearest typed condition identifiers")],
  ["target.sources.noise_type", typed(["design.noises[].noise_type"])],
  ["target.sources.tone_type", typed(["design.custom_looming_files[].tone_type", "design.prestimulus_files[].tone_type"])],
  ["target.sources.source_profile", typed(["design.noises[].source_profile"])],
  ["target.sources.source_sample_rate_hz", proxy(["design.trajectory.sample_rate"], "current field is a global render sample rate, not per-source file metadata")],
  ["target.sources.source_duration_ms", proxy(["design.custom_looming_files[].target_duration_s", "design.prestimulus_files[].target_duration_s"], "seconds-to-milliseconds transform exists for imported files, but generated-noise duration has no per-source typed field")],
  ["target.sources.source_gain_linear", typed(sourceGains)],
  ["target.sources.import_render_mode", typed(["design.custom_looming_files[].render_mode", "design.prestimulus_files[].render_mode"])],
  ["target.sources.source_motion_mode", typed(sourceMotionModes)],

  ["target.trajectories.trajectory_count", derived(sourceSnapshots, "count of source trajectory entities; no serialized trajectory-count scalar")],
  ["target.trajectories.trajectory_labels", proxy(sourceLabels, "source labels identify current source-level trajectory snapshots")],
  ["target.trajectories.trajectory_direction", proxy(["design.trajectory.path_direction", ...sourceSnapshots], "global typed default plus untyped per-source snapshots cannot provide a typed repeatable trajectory contract")],
  ["target.trajectories.coordinate_mode", proxy(["design.trajectory.coordinate_mode", ...sourceSnapshots], "global typed default plus untyped per-source snapshots cannot provide a typed repeatable trajectory contract")],
  ["target.trajectories.start_distance_cm", proxy(["design.trajectory.start_radius_m", ...sourceSnapshots], "centimetres-to-metres transform is typed only for the global trajectory; per-source values remain untyped")],
  ["target.trajectories.end_distance_cm", proxy(["design.trajectory.end_radius_m", ...sourceSnapshots], "centimetres-to-metres transform is typed only for the global trajectory; per-source values remain untyped")],
  ["target.trajectories.start_xyz_m", proxy(["design.trajectory.start_x_m", "design.trajectory.start_y_m", "design.trajectory.start_z_m", ...sourceSnapshots], "three global typed coordinates plus untyped per-source snapshots")],
  ["target.trajectories.end_xyz_m", proxy(["design.trajectory.end_x_m", "design.trajectory.end_y_m", "design.trajectory.end_z_m", ...sourceSnapshots], "three global typed coordinates plus untyped per-source snapshots")],
  ["target.trajectories.path_length_m", proxy(["design.trajectory.path_length_m", ...sourceSnapshots], "global typed value plus untyped per-source snapshots")],
  ["target.trajectories.speed_mps", proxy(["design.trajectory.propagation_speed_mps", ...sourceSnapshots], "global typed value plus untyped per-source snapshots")],
  ["target.trajectories.movement_duration_ms", derived(["design.trajectory.path_length_m", "design.trajectory.propagation_speed_mps"], "computed as path length divided by propagation speed")],
  ["target.trajectories.azimuth_start_deg", proxy(["design.trajectory.azimuth_start_deg", ...sourceSnapshots], "global typed value plus untyped per-source snapshots")],
  ["target.trajectories.azimuth_end_deg", proxy(["design.trajectory.azimuth_end_deg", ...sourceSnapshots], "global typed value plus untyped per-source snapshots")],
  ["target.trajectories.elevation_start_deg", proxy(["design.trajectory.elevation_deg", ...sourceSnapshots], "one global elevation scalar cannot encode distinct start/end or per-source elevations")],
  ["target.trajectories.elevation_end_deg", proxy(["design.trajectory.elevation_deg", ...sourceSnapshots], "one global elevation scalar cannot encode distinct start/end or per-source elevations")],
  ["target.trajectories.pre_hold_ms", proxy(["design.trajectory.padding_pre_s", ...sourceSnapshots], "seconds-to-milliseconds transform is typed only for the global trajectory")],
  ["target.trajectories.post_hold_ms", proxy(["design.trajectory.padding_post_s", ...sourceSnapshots], "seconds-to-milliseconds transform is typed only for the global trajectory")],
  ["target.trajectories.inverse_square_enabled", proxy(["design.trajectory.use_inverse_square", ...sourceSnapshots], "global typed switch plus untyped per-source snapshots")],
  ["target.trajectories.attenuation_gain_law", proxy(["design.trajectory.use_inverse_square", ...sourceSnapshots], "current global boolean selects only inverse-square on/off; per-source laws are untyped")],
  ["target.trajectories.distance_or_soa_anchor_table", composite(["design.protocol.soa_values_ms", "design.protocol.spatial_values_cm", "design.protocol.pair_spatial_values_with_soas"], "current global SOA/distance pairing")],

  ["target.rendering.sofa_hrir_asset", typed(["design.sofa_file"])],

  ["target.trial_sequence.trial_row_count", derived(["design.protocol.trial_strips[].strip_id"], "count of instantiated trial-strip entities")],
  ["target.trial_sequence.row_ids", typed(["design.protocol.trial_strips[].strip_id"])],
  ["target.trial_sequence.row_labels", typed(["design.protocol.trial_strips[].label"])],
  ["target.trial_sequence.row_order", proxy(["design.protocol.trial_strips[].strip_id"], "list order is implicit; no typed row-order field")],
  ["target.trial_sequence.row_audio_tactile_percentage", typed(["design.protocol.trial_strips[].audio_tactile_percentage"])],
  ["target.trial_sequence.row_catch_percentage", typed(["design.protocol.trial_strips[].catch_percentage"])],
  ["target.trial_sequence.row_baseline_percentage", typed(["design.protocol.trial_strips[].baseline_percentage"])],
  ["target.trial_sequence.row_soa_overrides_ms", typed(["design.protocol.trial_strips[].soa_values_ms"])],
  ["target.trial_sequence.row_spatial_overrides_cm", typed(["design.protocol.trial_strips[].spatial_values_cm"])],
  ["target.trial_sequence.sequence_elements", composite(["design.protocol.trial_strips[].elements[].element_id", "design.protocol.trial_strips[].elements[].kind", "design.protocol.trial_strips[].elements[].label", "design.protocol.trial_strips[].elements[].source_label", "design.protocol.trial_strips[].elements[].source_labels"], "typed element records")],
  ["target.trial_sequence.source_alternatives", typed(["design.protocol.trial_strips[].elements[].source_labels"])],
  ["target.trial_sequence.jitter_values_ms", typed(["design.protocol.trial_strips[].elements[].jitter_values_ms"])],
  ["target.trial_sequence.jitter_randomized", typed(["design.protocol.trial_strips[].elements[].randomized"])],
  ["target.trial_sequence.blocked_or_random_order", composite(["design.protocol.trial_randomization_strategy", "design.protocol.block_order_randomization"], "trial and block ordering are distinct current inputs")],

  ["target.tactile_protocol.tactile_present", proxy(["design.protocol.tactile_sites"], "presence is inferred from a non-empty site list")],
  ["target.tactile_protocol.tactile_site", typed(["design.protocol.tactile_sites"])],
  ["target.tactile_protocol.soa_values_ms", typed(["design.protocol.soa_values_ms", "design.protocol.trial_strips[].soa_values_ms"])],
  ["target.tactile_protocol.spatial_values_cm", typed(["design.protocol.spatial_values_cm", "design.protocol.trial_strips[].spatial_values_cm"])],
  ["target.tactile_protocol.pair_spatial_values_with_soas", typed(["design.protocol.pair_spatial_values_with_soas"])],
  ["target.tactile_protocol.distance_at_touch_values_cm", proxy(["design.protocol.spatial_values_cm", "design.protocol.trial_strips[].spatial_values_cm"], "current distance arrays do not independently name distance-at-touch semantics")],
  ["target.tactile_protocol.baseline_enabled", typed(["design.protocol.include_baseline_trials"])],
  ["target.tactile_protocol.baseline_strategy", typed(["design.protocol.baseline_strategy"])],
  ["target.tactile_protocol.baseline_soa_values_ms", typed(["design.protocol.baseline_soa_values_ms"])],
  ["target.tactile_protocol.baseline_custom_trial_mode", typed(["design.protocol.baseline_custom_trial_mode"])],
  ["target.tactile_protocol.catch_enabled", typed(["design.protocol.include_catch_trials"])],
  ["target.tactile_protocol.catch_type", proxy(["design.protocol.include_catch_trials"], "current protocol toggles catch trials but has no typed catch-type field")],
  ["target.tactile_protocol.auditory_only_enabled", typed(["design.protocol.include_auditory_only_trials"])],

  ["target.trial_pool.repetitions_per_condition", typed(["design.protocol.repetitions_per_condition"])],
  ["target.trial_pool.repetition_defaults_by_family", typed(["design.protocol.trial_pool_repetition_defaults"])],
  ["target.trial_pool.exact_family_counts", derived(["design.protocol.repetitions_per_condition", "design.protocol.trial_pool_repetition_defaults"], "materialized from repetition policy")],
  ["target.trial_pool.baseline_count_exact", typed(["design.protocol.baseline_trials_exact"])],
  ["target.trial_pool.baseline_percentage", typed(["design.protocol.baseline_trial_percentage"])],
  ["target.trial_pool.catch_count_exact", typed(["design.protocol.catch_trials_exact"])],
  ["target.trial_pool.catch_percentage", typed(["design.protocol.catch_trial_percentage"])],
  ["target.trial_pool.auditory_only_count_exact", typed(["design.protocol.auditory_only_trials_exact"])],
  ["target.trial_pool.auditory_only_percentage", typed(["design.protocol.auditory_only_trial_percentage"])],
  ["target.trial_pool.catch_crosses_sequence_variants", typed(["design.protocol.catch_crosses_sequence_variants"])],
  ["target.trial_pool.baseline_crosses_sequence_variants", typed(["design.protocol.baseline_crosses_sequence_variants"])],
  ["target.trial_pool.auditory_only_crosses_sequence_variants", typed(["design.protocol.auditory_only_crosses_sequence_variants"])],
  ["target.trial_pool.total_trial_count", derived(["design.protocol.repetitions_per_condition", "design.protocol.trial_pool_repetition_defaults", "design.protocol.baseline_trials_exact", "design.protocol.catch_trials_exact", "design.protocol.auditory_only_trials_exact"], "computed/materialized count, not a primary input")],

  ["target.block_design.block_count", typed(["design.protocol.blocks"])],
  ["target.block_design.block_labels", typed(["design.protocol.block_specs[].label"])],
  ["target.block_design.block_stimulus_types", typed(["design.protocol.block_specs[].stimulus_types"])],
  ["target.block_design.repeat_trial_pool_per_block", typed(["design.protocol.repeat_trial_pool_per_block"])],
  ["target.block_design.distribute_trial_pool_across_blocks", typed(["design.protocol.distribute_trial_pool_across_blocks"])],
  ["target.block_design.trial_randomization_strategy", typed(["design.protocol.trial_randomization_strategy"])],
  ["target.block_design.block_order_randomization", typed(["design.protocol.block_order_randomization"])],
  ["target.block_design.max_consecutive_same_trial_type", typed(["design.protocol.max_consecutive_same_trial_type"])],
  ["target.block_design.random_seed", typed(["design.protocol.random_seed"])],
  ["target.block_design.per_block_trial_counts", derived(["design.protocol.blocks", "design.protocol.block_specs[].stimulus_types"], "computed prepared-block output")],

  ["target.profile_finalization.participant_order_algorithm", untyped([P.participantOrder], "algorithm is an untyped key inside participant_order_policy")],
  ["target.profile_finalization.participant_order_version", untyped([P.participantOrder], "version is an untyped key inside participant_order_policy")],
  ["target.profile_finalization.participant_order_seed", untyped([P.participantOrder, "design.protocol.random_seed"], "policy object plus typed general random seed")],
  ["target.profile_finalization.order_preview_count", typed(["design.protocol.participants"], "legacy field name participants is consumed as order-preview count")],
]);

const SOURCE_PROFILE_CONTAINER_KEYS = new Set([
  "burst_count_mode", "burst_count", "burst_duration_ms", "burst_rise_fall_ms",
  "burst_period_ms", "burst_onset_ms", "burst_active_window_ms", "burst_spacing_policy",
]);
const SOURCE_SNAPSHOT_CONTAINER_KEYS = new Set([
  "trajectory_family", "coordinate_frame", "body_anchor", "body_part", "body_side",
  "spatial_hemifield", "body_relative_axis", "participant_posture", "head_trunk_facing",
  "gaze_fixation_eyes_policy", "source_room_positions", "movement_implementation",
]);
const ROW_METADATA_CONTAINER_KEYS = new Set([
  "sequence_variant_count", "sequence_variant_keys", "iti_policy", "iti_values_or_range_ms",
  "iti_distribution", "pre_sound_silence_ms", "post_sound_silence_ms", "foreperiod_ms",
  "condition_intermixing", "task_sequence_rules", "hazard_control_policy",
  "expectancy_control_role", "row_order_constraints", "within_family_queue_policy",
  "condition_blocking_or_intermixing",
]);
const REFERENCE_CONTAINER_GROUPS = new Set([
  "study_design", "renderer_loudness_visual_mr",
]);

export function targetCurrentBinding(parameter, currentInputPaths) {
  let result = EXPLICIT.get(parameter.parameterId);
  if (!result && SOURCE_PROFILE_CONTAINER_KEYS.has(parameter.key)) {
    result = untyped([P.sourceProfile], "untyped source_profile_parameters object");
  }
  if (!result && SOURCE_SNAPSHOT_CONTAINER_KEYS.has(parameter.key)) {
    result = untyped(sourceSnapshots, "untyped per-source trajectory_snapshot objects");
  }
  if (!result && ROW_METADATA_CONTAINER_KEYS.has(parameter.key)) {
    result = untyped([P.rowMetadata], "untyped trial-strip metadata object");
  }
  if (!result && REFERENCE_CONTAINER_GROUPS.has(parameter.groupId)) {
    result = untyped([P.reference], "untyped study_profile_reference_parameters object; exact key consumption is not guaranteed");
  }
  if (!result && parameter.provisionalRoutingHint === "freeform_metadata_only") {
    result = untyped([P.reference], "untyped study_profile_reference_parameters object; exact key consumption is not guaranteed");
  }
  if (!result) {
    return {
      currentBindingState: "not_in_current_design_serializer",
      currentSerializedPaths: [],
      bindingBasis: "no conservative binding to the current StimulusDesign parser/serializer was established",
    };
  }

  const missing = result.paths.filter((path) => !currentInputPaths.has(path));
  if (missing.length) {
    throw new Error(
      `Target crosswalk references unknown current input path(s) for ${parameter.parameterId}: ${missing.join(", ")}`,
    );
  }
  return {
    currentBindingState: result.state,
    currentSerializedPaths: result.paths,
    bindingBasis: result.basis,
  };
}
