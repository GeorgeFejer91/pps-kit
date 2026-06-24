# Study 5 Instruction Transcript Library

Source variant: `original_study5`

Source manifest: `assets/breathing/original_study5/spoken_assets_manifest.json`

This library records the participant-facing instruction text used by the Study 5 profile. The five run-level clips are owned by Segment 6 run setup, and the inhale/exhale cue clips are within-trial fixed audio used by the Segment 4/5 block schedule.

The run-level transcripts were generated locally from the decoded original Study 5 WAV assets with Whisper `small` and cross-checked with Whisper `base.en`. Segment timestamps are ASR estimates. The phrase `particles expand to their fullest capacity` appears in both ASR passes for `General_Instructions.wav` and is preserved here pending human auditory review or recovery of the original script.

## Run-Level Instructions

### General Instructions

Slot: `before_experiment`

Audio: `assets/breathing/original_study5/General_Instructions.wav`

Transcript:

> Go ahead and make yourself comfortable. During this experiment, we will practice a form of box breathing. You'll inhale through your nose for a count of four. Hold the breath for a count of four. Exhale through your nose for a count of four. And hold the breath for a count of four. Please make sure to inhale through your nose as deeply as possible over four seconds. Try to make sure the particles expand to their fullest capacity. Then, during the retention periods, you will at some times feel a vibration on your chest. As soon as you do, press the mouse button as fast as possible while maintaining accuracy. Please only press the mouse if you feel a vibration while ignoring all other tones. And finally, please make sure to always keep your mouth closed and only breathe in and out through your nose. Now let's practice this breathing for a bit. And once you have experienced what it feels like to expand the particles to their fullest capacity during inhalation, let the experimenter know that you are ready to begin the experiment.

### Pre-Block Instruction

Slot: `before_each_block`

Audio: `assets/breathing/original_study5/Pre-Block_Instruction.wav`

Transcript:

> Please remember to always keep your mouth closed and only breathe in and out through your nose. Ready? Let's go!

### Post-Block Instruction

Slot: `after_each_block`

Audio: `assets/breathing/original_study5/Post-Block_Instruction.wav`

Transcript:

> You have finished this block. Feel free to close your eyes for a moment and click the mouse button when you are ready to continue.

### Condition Transition

Slot: `between_conditions`

Audio: `assets/breathing/original_study5/InterimMessage.wav`

Transcript:

> You are now finished with part one of the experiment. Feel free to take a break and let the experimenter know when you are ready to continue with the second half.

### Finish Message

Slot: `after_experiment`

Audio: `assets/breathing/original_study5/FinishMessage.wav`

Transcript:

> Well done! You have finished the experiment. Feel free to take off the headset whenever you please.

## Within-Trial Instruction Cues

### Inhale Instruction

Trial phase: `Inhale`

Audio: `assets/breathing/original_study5/Inhale-2-3-4-hold_FIXED.wav`

Transcript:

> Inhale, two, three, four, hold.

### Exhale Instruction

Trial phase: `Exhale`

Audio: `assets/breathing/original_study5/Exhale-2-3-4-hold_FIXED.wav`

Transcript:

> Exhale, two, three, four, hold.
