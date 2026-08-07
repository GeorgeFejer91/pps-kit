# Publication-network data asset

`citation_snapshot.v1.json` is the tracked, public-safe input for the PPS
Toolkit's interactive publication/citation network. It contains the 1,712
publication nodes and 10,109 directed within-corpus citation edges from the
dated `pps-citation-network-20260807` research snapshot.

The corpus is a maximum-coverage, multi-index PPS-explicit snapshot with
citation context. It is not a claim that every PPS publication is present. The
generator projects this broad input into `publication_network.v2.json`, a
focused `pps-publication-citation-network.v2` browser asset containing only
experimental audio-tactile PPS papers covered by the Toolkit literature audit.

The focused projection includes a publication when at least one exact-DOI audit
record is not `adjacent_out_of_scope` and the publication is not classified as
a review. The current projection contains 64 publications, 68 in-scope task
records, and 456 induced citation edges. Fifteen publication nodes contain 17
runnable records; the remaining 49 publications have supported paradigms but
incomplete source parameters.

## Rebuild

Generate the dashboard asset from the tracked snapshot:

```bash
node tools/build_publication_network_asset.mjs
```

Refresh the source snapshot from a local research bundle, then rebuild:

```bash
node tools/build_publication_network_asset.mjs \
  --source-bundle /path/to/pps-citation-network-YYYYMMDD
```

Use `--source-snapshot`, `--snapshot-output`, and `--output` to direct inputs
and outputs to temporary paths for deterministic validation.

## Public-data boundaries

- Citation edges run from the citing publication to the cited publication.
- The broad v1 source retains all 1,712 publications, including its original
  101 manually confirmed audiotactile labels and provisional modality screens.
  The browser does not expose that broad discovery corpus; it uses the narrower
  DOI-linked Toolkit-audit rule above.
- Reviews and every `adjacent_out_of_scope` record are excluded from the focused
  browser asset. A supported paradigm means the Toolkit can represent the task
  structure, not that every original asset, apparatus setting, or reported
  parameter is available.
- Abstract text is included only when it can be reconstructed from an
  OpenAlex-attributed metadata record under OpenAlex's CC0 terms. Copyright in
  the underlying publication remains with its rights holder. Other abstracts
  are represented by an availability status, caveat, and publication link
  rather than copied text.
- PPS Toolkit literature and parameter audits are joined by normalized DOI
  only. All in-scope task records sharing a DOI are kept, and no fuzzy title or
  author matching is used.
- Citation counts and centrality values are corpus-local navigation metrics,
  not study-quality ratings or effect estimates.
- Raw provider responses, PDFs, supplements, and extracted full text are not
  part of this tracked asset.
