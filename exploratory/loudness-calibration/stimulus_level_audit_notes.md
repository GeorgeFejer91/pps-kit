# Stimulus Level Audit Notes

Generated with:

```powershell
python exploratory\loudness-calibration\analyze_stimulus_levels.py --root .
```

Generated files:

- `stimulus_level_audit.csv`
- `stimulus_level_audit.json`

## Current Study 5 Looming Results

All Study 5 looming WAVs are peak-normalized to about `-0.915 dBFS`, but they
are not matched in RMS. The Brown noise stimulus is much louder by RMS than the
other noise types.

| File | Peak dBFS | Full RMS dBFS | Last 500 ms RMS dBFS |
| --- | ---: | ---: | ---: |
| `looming_Blue_frontal.wav` | -0.915 | -20.862 | -13.743 |
| `looming_Brown_frontal.wav` | -0.915 | -13.697 | -5.167 |
| `looming_Pink_frontal.wav` | -0.915 | -20.304 | -13.229 |
| `looming_White_frontal.wav` | -0.915 | -20.410 | -13.285 |

The duplicated top-level and `02_looming_stimuli/` copies have matching values.

## Current Breathing/Instruction Results

The audited breathing and instruction files are also near peak-normalized, with
peaks around `-1.15` to `-0.75 dBFS`. Full-file RMS spans about `-20.03` to
`-13.39 dBFS`.

The currently loudest instruction by full-file RMS is the original Study 5
`InterimMessage.wav` at about `-13.39 dBFS`; the current Kokoro/root inhale
instruction is about `-15.50 dBFS`.

## Implication

Peak normalization alone is not a valid loudness policy for this experiment.
The next implementation step should normalize or gain-tag Study 5 looming
stimuli by a calibrated RMS window while preserving the within-stimulus looming
envelope. A practical first target is to match the final 500 ms RMS of all four
looming noise types within +/- 1 dB, then set instruction RMS lower by the
configured offset.
