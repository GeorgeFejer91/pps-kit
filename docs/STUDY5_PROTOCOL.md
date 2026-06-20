# Study 5 Protocol Notes

This toolkit packages the audio-tactile peripersonal-space task used for Study 5.

## Timing Contract

- spoken breathing instruction: exactly 4.000 s
- looming stimulus segment: exactly 4.000 s
- full trial: exactly 8.000 s
- tactile cue duration: 100 ms
- tactile SOAs: 0, 300, 800, 1500, 2200, 2700 ms
- looming approach: 110 cm to 10 cm over 3 s, embedded in a 4 s stimulus window

## Trial Families

- audio-tactile trials: looming noise plus tactile cue
- baseline trials: tactile cue without looming
- catch trials: looming noise without tactile cue

## Respiratory Phases

The public assets include both British Kokoro `bf_emma` instruction WAVs and the original Study 5 instruction audio decoded from local lab MP3 assets. The default Study 5 preload uses the original 4-second inhale/exhale pair, and the British Kokoro pair remains available as alternate fixed audio. The generator combines whichever 4-second inhale/exhale instruction pair is selected with stimulus segments to create 8-second trials.

## Preload Instruction Audio Clips

Study 5 also preloads run-level instruction audio in Segment 6 under **Preload
Instruction Audio Clips**. These clips are separate from the 4-second
inhale/exhale within-trial clips:

- before experiment: `General_Instructions.wav`, 85.708 s
- before each block: `Pre-Block_Instruction.wav`, 8.418 s
- after each block: `Post-Block_Instruction.wav`, 8.829 s
- between conditions: `InterimMessage.wav`, 10.109 s
- after experiment: `FinishMessage.wav`, 7.001 s

The dashboard saves these choices in the Segment 6 run setup profile, publishes
them into `experiment_run_setup_manifest.json`, and copies enabled clips into
each participant session's `instructions\` folder. Focus Mode logs
`instruction_start`, `instruction_end`, and `instruction_continue` events; a
click used only to continue an instruction is not counted as a trial response.

## Prebaked Looming Assets

Study 5 also includes owned 4-second auditory-only looming WAVs for the pink, blue, white, and brown frontal sources under `assets/preloads/study5_box_breathing_pps/02_looming_stimuli/`. These files are binaural/source stimuli only; tactile events are still introduced later from the SOA schedule during session preparation.

The additional bundled profile `study5_box_breathing_pps_pink_white` is a Study 5 lab variant created through the dashboard Edit-mode source-removal workflow. It keeps only the original pink and white frontal looming WAVs, prunes blue and brown from the Segment 2 decision pool, and leaves the remaining Study 5 timing, SOA, baseline/catch, instruction, trajectory, block, participant, and repetition defaults unchanged.

The preload asset inventory lives at `assets/preloads/preload_inventory.json`, with a Study 5 profile manifest at `assets/preloads/study5_box_breathing_pps/preload_manifest.json`. Each preload profile uses the same local file-cabinet structure as the HTML dashboard: `01_profile`, `02_looming_stimuli`, `03_baseline_strategy`, `04_trial_designer`, and `05_run_setup`. The dashboard/backend use this inventory to verify local assets and read source, trajectory, baseline, trial, and run-default metadata.

## Dashboard Preload

The HTML dashboard profile `study5_box_breathing_pps` is the unpublished local Study 5 preload. It is separate from published-study profiles such as Canzoneri et al. (2012) and preloads both instruction variants, bundled 4-second auditory-only looming source WAVs, and the default `Inhale instruction | Looming Stimulus` and `Exhale instruction | Looming Stimulus` within-block trial type rows. The rows are logged as `trial_type_label` values and scheduled sequentially top-to-bottom, so Study 5 plays the inhale trial type followed by the exhale trial type. Instruction snippet loading and selection belong in the Trial Designer segment, not in the Looming Stimuli Builder.

This profile is the default dashboard startup profile. Fresh launches and scratch-custom startup states initialize from Study 5 so the current lab workflow is ready without selecting a profile manually.

Study 5 defaults to a two-condition Segment 6 run setup. The saved CSV keeps
the internal phases as `pre` and `post` for analysis compatibility, while the
dashboard labels them as Condition 1 and Condition 2.

## Data Outputs

The runner stores loopback recordings and demographics locally. The decoder reconstructs trial timing from WAV recordings, then writes diagnostics, final CSVs, and summaries under the decoded artifact directory.
