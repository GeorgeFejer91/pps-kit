# DynaSpace Spectral Feature Audit

This folder contains a derived, redistributable audit of the smartphone
DynaSpace PPS audio files against the PPS-kit generated proxy stimuli. It also
records the Consensus/browser and Consensus MCP evidence trail used to adopt the
best-of-both-worlds source-plus-renderer protocol as the PPS-kit standard for
newly generated looming stimuli.

The upstream DynaSpace WAV files are not copied into this repository. To
reproduce the measurements, keep a sibling private checkout named
`dynaspace-private`, or pass `--dynaspace-root` to:

```powershell
py For-AI/research/literature/docs/dynaspace_spectral_feature_audit/measure_dynaspace_audio.py
```

Primary outputs:

- `dynaspace_audio_feature_metrics.json`: full derived measurements.
- `dynaspace_audio_feature_summary.csv`: compact measured feature table.
- `looming_feature_comparison_matrix.csv`: raw looming versus PPS proxy deltas.
- `consensus_search_export.tex`: compact Consensus search export and MCP paper
  URL inventory.
- `dynaspace_spectral_feature_audit.tex`: TeX report source.
- `dynaspace_spectral_feature_audit.pdf`: compiled report.
