# DynaSpace Spectral Feature Audit

This folder contains a derived, redistributable audit of the smartphone
DynaSpace PPS audio files against the PPS-kit generated proxy stimuli.

The upstream DynaSpace WAV files are not copied into this repository. To
reproduce the measurements, keep a sibling private checkout named
`dynaspace-private`, or pass `--dynaspace-root` to:

```powershell
py docs/dynaspace_spectral_feature_audit/measure_dynaspace_audio.py
```

Primary outputs:

- `dynaspace_audio_feature_metrics.json`: full derived measurements.
- `dynaspace_audio_feature_summary.csv`: compact measured feature table.
- `looming_feature_comparison_matrix.csv`: raw looming versus PPS proxy deltas.
- `dynaspace_spectral_feature_audit.tex`: TeX report source.
- `dynaspace_spectral_feature_audit.pdf`: compiled report.

