# Publication-network data asset

`citation_snapshot.v1.json` is the tracked, public-safe input for the PPS
Toolkit's interactive publication/citation network. It contains the 1,712
publication nodes and 10,109 directed within-corpus citation edges from the
dated `pps-citation-network-20260807` research snapshot.

The corpus is a maximum-coverage, multi-index PPS-explicit snapshot with
citation context. It is not a claim that every PPS publication is present.

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
- The 101 audiotactile nodes marked verified come from the original manual
  audit. Other nodes are not silently inferred to be audiotactile.
- Verified audiotactile nodes carry deterministic subset-specific citation-map
  and publication-year coordinates. These fit the 101-node induced subgraph
  (78 connected nodes plus 23 nodes with no within-subset link) without changing
  the underlying papers, citation direction, or complete-corpus metrics.
- The 164 visuotactile lexical matches are provisional candidates with
  `verified: false`; none is presented as verified without a dedicated manual
  audit.
- Abstract text is included only when it can be reconstructed from an
  OpenAlex-attributed metadata record under OpenAlex's CC0 terms. Copyright in
  the underlying publication remains with its rights holder. Other abstracts
  are represented by an availability status, caveat, and publication link
  rather than copied text.
- PPS Toolkit literature and parameter audits are joined by normalized DOI
  only. The 73 study-level audit records map to 69 publication nodes; all
  records sharing a DOI are kept, and no fuzzy title or author matching is
  used. The asset includes 24 manual parameter reviews across 21 nodes.
- Raw provider responses, PDFs, supplements, and extracted full text are not
  part of this tracked asset.
