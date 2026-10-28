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

Re-capture after any template, preload or frontend change before relying on
native results. The initial baseline also exposes stale committed Canzoneri
source-duration metadata; its final outcome must use the coordinator's coherent
preload correction, rather than manually patching a captured plan.
