# Publication-network data asset

`citation_snapshot.v1.json` is the tracked, public-safe input for the PPS
Toolkit's interactive publication/citation network. It contains the 1,712
publication nodes and 10,109 directed within-corpus citation edges from the
dated `pps-citation-network-20260807` research snapshot.

The corpus is a maximum-coverage, multi-index PPS-explicit snapshot with
citation context. It is not a claim that every PPS publication is present. The
generator projects this broad input into `publication_network.v3.json`, a
focused `pps-publication-citation-network.v3` browser asset containing 94
non-review audio-tactile publications and 750 tracked citation links. The
generator preserves all 571 induced links in the frozen snapshot and adds the
127 non-overlapping links in
`openalex_audiotactile_citation_overlay.20260808.json`. That overlay records an
exact-DOI OpenAlex refresh for all 94 displayed records, including
query fields, capture date, endpoint scope, and expected union counts. The
subsequent `primary_source_citation_overlay.20260808.json` contains 60 citation
facts verified directly in the reference lists of six records that remained
provider-isolated; 52 have both endpoints in the displayed set. It records
source URLs and audit notes without redistributing full text. Candidate scope
comes from either the original manually confirmed audio-tactile audit (93
publications after review removal) or a later exact-DOI Toolkit literature audit
(4 additions). Display eligibility additionally requires a resolver-confirmed,
internally consistent canonical DOI link and provider-backed citation metadata, leaving 90
legacy-confirmed records plus the 4 later additions. A finite provider count of
zero is valid metadata. Toolkit readiness is an encoding, not an inclusion gate.

The detailed Toolkit assessment remains 15 runnable, 49 supported but parameter-
incomplete, 29 not yet assessed, and 1 adjacent/scope-conflict publication. The
map reduces that to two visual states: 15 implemented and 79 not implemented
yet. The default deterministic force layout uses one continuous rule for every
paper: citation neighbours attract, all nodes repel and share weak centering,
and radius-aware collision separation keeps them distinct on a square canvas.
The declared normalized edge-to-edge clearance is `0.015`. The 91-node main
component spreads broadly across the map; the 3 records with no verified
within-map link are not assigned to a perimeter. Node area encodes normalized
displayed-network citations received: radii run from `0.009` for the least-cited
nodes to `0.024` for the most-cited node, using a monotonic log-normalized area
scale. The alternative layout anchors horizontal position to year.

## Rebuild

Generate the dashboard asset from the tracked snapshot and tracked citation
overlays:

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
- The broad v1 source retains all 1,712 publications, including 101 manually
  confirmed audiotactile labels and provisional modality screens. The browser
  excludes reviews and shows only the 94-publication DOI- and metadata-eligible
  projection drawn from 97 verified/audited candidates.
- One included exact-DOI record is retained as `adjacent_scope_conflict` so the
  audit disagreement stays visible. A supported paradigm means the Toolkit can
  represent the task structure, not that every original asset, apparatus
  setting, or reported parameter is available.
- Abstract text is included only when it can be reconstructed from an
  OpenAlex-attributed metadata record under OpenAlex's CC0 terms. Copyright in
  the underlying publication remains with its rights holder. Other abstracts
  are represented by an availability status, caveat, and publication link
  rather than copied text.
- PPS Toolkit literature and parameter audits are joined by normalized DOI
  only. All in-scope task records sharing a DOI are kept, and no fuzzy title or
  author matching is used.
- Every tracked within-map link stays visible; selecting a node distinguishes
  incoming from outgoing citations. A missing line means only that the dated
  provider and primary-source audits captured no resolvable link inside this
  94-paper projection. Citation counts, node area, and centrality remain
  corpus-local navigation encodings, not study-quality ratings or effect estimates.
- Raw provider responses, PDFs, supplements, and extracted full text are not
  part of this tracked asset.
