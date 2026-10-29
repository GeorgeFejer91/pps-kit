# Shipped preset and archive audit

The audit population is every JSON file in
`packages/pps-resources/study_templates`, joined to the saved preload status and
the public study projection. Archive publications, study/context rows, presets,
and prepared participant sessions are different units. A publication or adjacent
context row without a preset is not an executable experiment.

The initial `613c1542` snapshot contains 94 publications, 178 study/context rows,
and 30 presets (28 published, two local). Sixteen publications and 21 study rows
have preset links. Twenty-five presets have a configuration-eligible saved gate;
five are blocked. These categories do not establish published-method fidelity,
native execution or physical timing.

## Reproduce the inventory

Run the existing compiled Designer in a local muted Chromium instance. The
capture uses ordinary preset navigation and the public `PPSDesignerApp` read
APIs. It does not inject state, override repetitions, change instruction slots,
accept native plans or play audio. Use the repository's installed Playwright
module, or set `PPS_PLAYWRIGHT_MODULE` to an existing module location.

```powershell
node For-AI/engineering/validation/scripts/capture_preset_plans.mjs
python For-AI/engineering/validation/scripts/audit_preset_population.py
python -m pytest -q For-AI/engineering/tests/test_preset_population_audit.py
```

Ignored outputs live in `artifacts/preset-functional-audit/`. Each preset has a
complete design, sequence-variant map, trial pool and source-block plan. The
capture report pins raw template, compiled frontend, preload inventory and
capture hashes. The population report rejects stale inputs, omitted or duplicate
presets, wrong identities, truncated blocks, missing/duplicated pool rows, and
changed timing/family/condition fields. Its archive table retains every study
row and each row's parameter-status counts.

The baseline real-browser pass captured all 25 eligible complete plans and all
five expected blocked plans, without browser exceptions. Both local Study 5
presets contain 204 source rows, six source blocks, a pre/post policy and five
enabled instruction slots. Native preparation must preserve both complete parts;
a single-trial or one-block fixture does not verify that preset. Descriptive
participant-order previews are not native acceptance receipts.

## Native acceptance boundary

The native audit consumes each complete captured plan with verified original
shipped or explicitly generated assets. It must report actual materialized row,
block, instruction and part counts, production package verification, every
compiled block schedule, and callback/result execution separately. A successful
missing-input rejection is a guard result, never a usable Runner file. Record
native failures as failures even when the metadata gate claimed eligibility.
The population report starts those observations as `not_assessed`; browser
capture alone cannot promote them.

Prior software evidence includes all-template tactile containment checks and a
complete 408-row Study 5 native preparation. Neither is evidence that all 25
eligible presets already passed native assembly or complete execution. Preserve
full plans in each additional case; do not replace them with a generic miniature
schedule. One representative participant may exercise a preset's complete
configured parts, while the native order planner must still account for every
saved participant order. State this distinction in receipts.

## Scientific and missing-input boundaries

All five saved gates have non-hardware gaps. Ferri artificial lacks the original
auditory file/envelope; Ferri ecological lacks the ecological sources/envelopes;
Taffou lacks original animal sounds, matching settings and filter identity;
Serino 2007 also lacks source recipe, ITI/jitter and response-window information;
Teneggi Experiment 3 lacks repetition/catch/block counts and retains substituted
sound and unimplemented cooperative-game context. The latter two also name
electrical/voice-key apparatus. Deferring new physical calibration does not
resolve the non-hardware gaps or make a default a reported parameter.

The shipped Matsuda browser plan has 200 source rows spread across four blocks;
the reviewed source describes 800 across four direction acquisitions. This
audit retains the shipped count and does not call successful software execution
a full-paper reproduction. Source contradictions, approximate assets and partial
parameters remain visible through the frozen catalogue. No native or physical
qualification status is changed by this audit.

Other concrete baseline differences are Noel bodily-self front/back (108 rows
spread over two blocks rather than 108 per stroking condition, 216 total),
Barumerli Experiments 1/2 (226/210 rows over four blocks rather than the reported
760/640 and additional tactile-only blocks), and Roussel (72 rows in one block
rather than six 72-row blocks). The source's Barumerli ordering and Roussel catch
contradictions remain unresolved. Each preset's report includes its linked
reviewed allocation/order contracts with primary source pointers, so software
results can be assessed against these limits without modifying scientific data.

Four published presets have no study-level mapper assignment: Noel walking,
Canzoneri tool use/amputation, and Galli wheelchair. Their registry entries retain
combined-profile disaggregation limits. They remain part of the 30-preset file
audit; no experiment mapping is invented here. Biggio's separate racket presets
and Collignon's separate posture presets each cover a condition, not the whole
multi-condition publication protocol by themselves.

Re-capture after any template, preload or frontend change before relying on
native results. The initial baseline exposes a frontend duration defect:
generated premade sources lack a hydrated duration, so `staticSourceInventory`
falls back to four seconds. Twenty-five presets / 38 source entries differ from
their actual bundled WAV durations. Canzoneri's source WAVs and preload metadata
are correctly three seconds, but the base generated source is planned as four;
the appended receding custom source retains three. This is a software defect,
not a missing scientific parameter. Fix its owning frontend source and re-capture;
do not manually patch captured plans or audio to make native checks pass.

A second baseline handoff defect affects nine eligible presets: the browser
trial-file/pool/block projections drop declared strip metadata that the existing
Python `ROW_CONTRACT_FIELDS` owner preserves. This includes the Collignon
presets' left/right choice set and correct answer, response rules, and task
context. Native assembly copies the resulting rows into its CSV. The report
compares every declared allowlisted field to the complete plan, accounting for
the established catch-family withholding override, and reports each affected
row count. A complete numerical trial pool does not compensate for a lost
response contract. Native result checks must verify response-to-trial identity
and scoring, not only that a response event was observed.

The same review found that the initial native assembler concatenates each trial
variant without the saved numeric `iti_ms` silence that the Python assembler
appends. This affects, for example, Biggio's configured 300 ms default and
Collignon's configured 1950 ms mean. Preserving these fields in CSV is necessary
but insufficient: native output and trial bounds must include the configured
interval, or reject it explicitly. That does not establish an unreported jitter
distribution. The native callback audit must compare input-to-trial identity,
expected synthetic scores and RTs, including explicitly supported choice and
auditory-only target policies; generic observed-response counts alone are not
that evidence.

Independent re-capture after the UI duration correction `f19e693a` (with download
checkpoint `09062da1`) again covers all 30 presets. All 44 generated premade
source durations match actual WAV headers; Canzoneri rows are now 5000 ms in
both directions. Source-row multiplicities are unchanged. Outputs are retained
separately under ignored `artifacts/preset-functional-audit-duration-fixed/`;
the nine saved-metadata losses remain present in that intermediate snapshot.

The subsequent `af7a3b3a` frontend checkpoint was independently captured through
the same public APIs into ignored `artifacts/preset-functional-audit-contract-fixed/`.
All 30 cases pass the capture contract: 25 complete plans, five explicit gates,
4740 source rows and 61 source blocks, with no browser exceptions. All 80
referenced stimulus WAV headers (44 generated/noise entries and 36 custom
entries, including native IEEE-float assets) agree with captured durations.
Declared allowlisted metadata now survives every complete plan. The reusable
population audit checks both properties; its focused suite has eight passing
checks. The capture report SHA256 is
`5d1c4961ddba24d4dd0113bb40fd3b579f93be67a375baea01e14753791ebed3`.

Block names remain a separate observed contract loss. Thirteen presets replace
33 descriptive saved block labels with generic `Block NN` labels; the two
Study 5 presets additionally change 12 numerical labels from `Block N` to
`Block NN`, which the report distinguishes as formatting only. Six presets
(Barumerli Experiments 1/2, Matsuda, Noel bodily-self front/back, and Pfeiffer)
lose 19 explicitly different condition labels. The remaining descriptive
labels identify the single-condition Biggio/Collignon presets or named
Noel-walking/Roussel blocks. This audit does not infer condition assignments,
stimulus direction, cohort multiplicity or repetition counts from those labels,
and does not repair the captures. Native materialization must preserve the
accepted full saved plan while reporting this limitation; numerical row
coverage alone is not evidence that the original condition contract survives.

The native ITI/metadata and response-control followups `ff695ac5` and `ddff1b5c`
passed an independent read-only review. That review is not execution evidence:
the archive report still marks native preparation and execution unassessed
until the exact captures pass the owning full-profile native sweep.
