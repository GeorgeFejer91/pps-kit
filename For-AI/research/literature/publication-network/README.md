# Publication-network data asset

`citation_snapshot.v1.json` is the tracked, public-safe input for the PPS
Toolkit's interactive publication/citation network. It contains the 1,712
publication nodes and 10,109 directed within-corpus citation edges from the
dated `pps-citation-network-20260807` research snapshot.

The corpus is a maximum-coverage, multi-index PPS-explicit snapshot with
citation context. It is not a claim that every PPS publication is present. The
generator projects this broad input into `publication_network.v3.json`, a
focused `pps-publication-citation-network.v3` browser asset containing 94
non-review audio-tactile candidate publications and 750 tracked citation links. The
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
The frozen publication set also retains reviewed adjacent boundaries. The
coverage source explicitly marks Finisguerra (2015) as a retained frozen boundary:
its auditory-TMS/MEP endpoint is outside direct audio-tactile replication, while
its publication identity and citation links remain in the map. That flag only
preserves membership; the record stays out of scope and gains no readiness.

The legacy Toolkit assessment contains 16 publication nodes labelled runnable,
46 supported but parameter-incomplete, 29 not yet assessed, and 3 adjacent/scope-
conflict publications. These are coarse template/encoding labels, not scientific parameter
completion or native qualification. The 2026-10-27 regeneration incorporates the
existing Canzoneri tool-use review (10.1007/s00221-013-3532-2; review dated
2026-07-16): one additional reviewed publication and record, with two combined
experiment orientation rows that still require experiment-specific checking.
No citation nodes or edges were added. The legacy map reduces its status to
16 implemented and 78 not implemented yet. The default deterministic force layout uses one continuous rule for every
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
node For-AI/research/literature/tools/build_publication_network_asset.mjs
```

Refresh the source snapshot from a local research bundle, then rebuild:

```bash
node For-AI/research/literature/tools/build_publication_network_asset.mjs \
  --source-bundle /path/to/pps-citation-network-YYYYMMDD
```

Use `--source-snapshot`, `--snapshot-output`, and `--output` to direct inputs
and outputs to temporary paths for deterministic validation.

## Public study evidence

`apps/designer/frontend/publication_study_reviews.v1.json` is a separate
`pps-publication-study-reviews.v1` projection. Its authority runs in one direction:
network identities → study registry and primary reviews → the compact
component-gated resolver → public review JSON. It never feeds the network
generator. Rebuild it with the existing review-matrix command:

```bash
node For-AI/research/literature/tools/build_publication_parameter_review_matrix.mjs
```

The public JSON exposes `publications` keyed by `networkNodeId` and `studies`
keyed by stable `studyRowId`, with eleven `contracts` per registered row. Each
contract carries its final evidence `status`, short factual `value`, separately
labelled `compositeValue`, source DOI URL, page/section, review date, missing
components and component evidence. `sourceUrl` preserves the DOI identity;
`evidenceSourceUrl` links the actual reviewed public source when a single safe
HTTP(S) pointer exists, and `sourceType` identifies its evidence layer/version.
Local, composite and credentialed source pointers are omitted, not published.
`templateIds` means a profile link exists;
it does not alter `parameterStatusCounts`. `studyRowAliases` resolves a superseded placeholder to its explicit experiment
children; a one-to-many alias is not equivalence to either child alone.
`nativeQualification` remains
`not_assessed` even for fully resolved paper evidence. Online actions are
limited to `prepare` and `preview`.

`inventoryAudit` separately counts registered inventories, Methods-backed
inventories, audited access blockers, and publications with eleven explicit
source dispositions for every retained row. Its machine-readable row ledger is
`publication_inventory_audit.csv` beside the compact matrices. Registry presence,
abstract counts and inherited coarse fields cannot pass that audit gate.
An eligible inventoried author version may retain an explicit final-comparison
gap; an inaccessible source requires dated actual attempts and an unresolved
publication review unit. Neither disposition establishes runnable replication
or native qualification. New registry entries need an explicit
`inventory_evidence_status`; missing classification stays open.
Each `publications[]` entry also exposes an `inventoryAudit` object with
`registered`, `evidenceStatus`, `inventoryStatus`, `studyRowCount`,
`rowsWithElevenSourceDispositions`, `allRowsHaveElevenSourceDispositions`, and
`inventoryAndContractsAudited`. The three yes/no decisions are JSON booleans;
the two row counts are integers. This public projection omits the private source
paths that can appear in the internal inventory evidence pointers.

The projection selects public fields explicitly and rejects local source/runtime
paths in review text; it preserves HTTP source URLs and DOI strings. It includes
neither raw PDFs nor private paths, generated runtime values, or participant data.
Unassessed experiments stay unassessed. Temporary matrix builds (`--output`)
do not write the canonical public asset unless `--public-output <file>` is
explicitly supplied. Focused tests compare every projected status/value against
the finalized evidence ledger and compare regenerated bytes against the asset.

## Public-data boundaries

- Citation edges run from the citing publication to the cited publication.
- The broad v1 source retains all 1,712 publications, including 101 manually
  confirmed audiotactile labels and provisional modality screens. The browser
  excludes reviews and shows only the 94-publication DOI- and metadata-eligible
  projection drawn from 97 verified/audited candidates.
- Two included exact-DOI records are retained as `adjacent_scope_conflict` so the
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

The 2026-10-27 primary review of Serino (2009), DOI
`10.1371/journal.pone.0006582`, corrects its coverage disposition to adjacent
auditory/TMS mechanistic context while retaining the node and citation edges.
Its two experiment rows replace one unassessed study placeholder through an
explicit alias. Sound-to-TMS timings must never become tactile SOAs.
