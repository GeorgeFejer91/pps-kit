export const DESIGNER_SEGMENTS = Object.freeze([
  {
    index: 0,
    step: "study",
    key: "0_profile",
    label: "Study project registry",
    folderName: "0_profile",
    manifestName: "project_manifest.json",
    upstreamKey: "",
    targetId: "study-segment",
  },
  {
    index: 1,
    step: "stimulus",
    key: "1_core_audio_ingredients",
    label: "Core audio ingredients",
    folderName: "1_core_audio_ingredients",
    manifestName: "stimulus_ingredients_manifest.json",
    upstreamKey: "0_profile",
    targetId: "stimulus-segment",
  },
  {
    index: 2,
    step: "trials",
    key: "2_trial_sequence_designs",
    label: "Trial sequence designs",
    folderName: "2_trial_sequence_designs",
    manifestName: "trial_sequence_variants_manifest.json",
    upstreamKey: "1_core_audio_ingredients",
    targetId: "trials-segment",
  },
  {
    index: 3,
    step: "baseline",
    key: "3_tactile_and_baseline_trials",
    label: "Tactile and baseline trial files",
    folderName: "3_tactile_and_baseline_trials",
    manifestName: "baseline_tactile_trial_files_manifest.json",
    upstreamKey: "2_trial_sequence_designs",
    targetId: "baseline-segment",
  },
  {
    index: 4,
    step: "block",
    key: "4_trial_repetition_pool",
    label: "Trial repetition pool",
    folderName: "4_trial_repetition_pool",
    manifestName: "trial_repetition_pool_manifest.json",
    upstreamKey: "3_tactile_and_baseline_trials",
    targetId: "block-segment",
  },
  {
    index: 5,
    step: "schedule",
    key: "5_block_csv_preview",
    label: "Block CSV preview",
    folderName: "5_block_csv_preview",
    manifestName: "block_csv_preview_manifest.json",
    upstreamKey: "4_trial_repetition_pool",
    targetId: "schedule-segment",
  },
  {
    index: 6,
    step: "run",
    key: "6_experiment_run_setup",
    label: "Profile validation and save",
    folderName: "6_experiment_run_setup",
    manifestName: "experiment_run_setup_manifest.json",
    upstreamKey: "5_block_csv_preview",
    targetId: "run-segment",
  },
].map((segment) => Object.freeze(segment)));

export const WORKFLOW_STEPS = Object.freeze(DESIGNER_SEGMENTS.map((segment) => segment.step));
export const STEP_TARGETS = Object.freeze(
  Object.fromEntries(DESIGNER_SEGMENTS.map((segment) => [segment.step, segment.targetId])),
);
export const STEP_SEGMENT_FOLDERS = Object.freeze(
  Object.fromEntries(DESIGNER_SEGMENTS.map((segment) => [segment.step, segment.folderName])),
);
export const NEXT_STEP = Object.freeze(
  Object.fromEntries(DESIGNER_SEGMENTS.slice(0, -1).map((segment, index) => [segment.step, DESIGNER_SEGMENTS[index + 1].step])),
);

export function segmentForStep(step) {
  return DESIGNER_SEGMENTS.find((segment) => segment.step === step) || null;
}
