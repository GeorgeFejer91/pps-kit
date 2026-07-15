# Protocol 12: Published Profile Recreation Interface Validation

## Purpose

Validate that the PPS Toolkit interface can recreate published audio-tactile
experiment profiles from tracked preload/profile metadata. This protocol proves
that a profile can move from the published-study preload gate through local
Segment 0-6 materialization and runner handoff artifacts before it is used in
Protocol 11 runner stress.

This is a parameter-recreation and interface-validation protocol. It does not
claim to redistribute, recover, or exactly reproduce original private author
stimuli.

## Scope

Use ignored validation folders only. Store generated outputs under:

```text
artifacts/validation_runs/
local_data/validation_runs/
```

Ready profiles are the entries in
`assets/preloads/profile_recreation_status.json` with:

- `runner_readiness = ready`
- `profile_checks_passed = true`
- `segment_0_to_4_profile_checks_passed = true`

Blocked profiles must remain blocked and must expose concrete missing-parameter
or toolkit-structural reasons.

## Harness

Run the ready published-profile matrix:

```powershell
python .\validation_protocols\scripts\run_profile_recreation_interface_matrix.py `
  --output-dir artifacts\validation_runs\profile_recreation_interface_matrix_current
```

Run all ready profiles, including the local Study 5 control:

```powershell
python .\validation_protocols\scripts\run_profile_recreation_interface_matrix.py `
  --profile-set ready-all `
  --output-dir artifacts\validation_runs\profile_recreation_interface_matrix_ready_all
```

Run a fast metadata-only gate check:

```powershell
python .\validation_protocols\scripts\run_profile_recreation_interface_matrix.py `
  --metadata-only `
  --output-dir artifacts\validation_runs\profile_recreation_interface_metadata_current
```

## Success Criteria

### Profile Gate And Provenance

- [ ] Every tested profile has
  `01_profile/profile_parameters_manifest.json`.
- [ ] Manifest schema is `pps-study-profile-parameters.v1`.
- [ ] Profile appears in `profile_recreation_status.json`.
- [ ] Ready profiles have no missing publication parameters and no unsupported
  toolkit structures.
- [ ] Blocked profiles remain non-ready and expose concrete blocker reasons.
- [ ] Published profiles carry citation/DOI/source provenance when available.
- [ ] Manifests state that the toolkit recreates reported parameters rather
  than redistributing exact original author stimuli.

### Interface Selection And Profile State

- [ ] The dashboard/local companion exposes ready published profiles in the
  study/profile preload selector.
- [ ] Selecting a profile sets the active `template_id`.
- [ ] Published profiles are read-only for direct mutation.
- [ ] `Edit As New Study` is the route for modifying a published preload.
- [ ] Blocked or unfinished profiles cannot be launched as ready profiles.
- [ ] Hosted/static mode can inspect committed profile metadata but cannot
  bake, materialize, or launch without the local companion.

### Segment 0-6 Materialization

- [ ] Segment 0 creates or activates a writable project folder under local
  validation output or `local_data/...`.
- [ ] Segment 1 materializes source/trajectory ingredients and manifests.
- [ ] Segment 2 materializes non-empty trial sequence rows.
- [ ] Segment 3 materializes tactile, baseline, and catch trial WAVs according
  to the profile.
- [ ] Segment 4 materializes the repetition-pool CSV and manifest.
- [ ] Segment 5 generates and accepts block CSVs.
- [ ] Segment 6 writes an experiment run setup manifest and CSV.
- [ ] No generated project/session artifacts are written under read-only
  `assets/preloads/`.

### Parameter Fidelity

- [ ] Materialized artifacts match profile identity, citation, DOI, and variant
  label.
- [ ] Auditory source labels, trajectory metadata, duration, spatial values,
  and renderer/gain caveats match the profile manifest.
- [ ] Trial row order and trial-strip labels match the profile manifest.
- [ ] Fixed-audio, looming-stimulus, and jitter/ITI box order match the profile
  manifest.
- [ ] SOA table, tactile timing, baseline strategy, and catch-trial policy
  match the profile manifest.
- [ ] Repetition counts and expected trial-pool totals match the profile
  manifest.
- [ ] Block counts and Segment 6 participant defaults match the run setup.

### Stimulus Artifact Checks

- [ ] All referenced WAVs exist under writable local profile/session paths.
- [ ] WAVs are readable PCM.
- [ ] Channel counts match stage expectations.
- [ ] Sample rates are consistent inside each assembled block.
- [ ] Durations and sample columns recompute from manifest timing.
- [ ] Audio-tactile and baseline rows contain tactile cues as declared.
- [ ] Catch rows contain no tactile cue.
- [ ] Source hashes match when hashes are declared.

### Visual And Mouse-Driven UI Evidence

- [ ] Browser or Qt mouse clicks exercise profile selection and Segment actions
  when declaring a profile UI-ready.
- [ ] Screenshots are captured after key visual state changes.
- [ ] Screenshots are nonblank and show the expected selected profile/state.
- [ ] Profile blocker states are visible and actionable.

### Runner Handoff Smoke

- [ ] Segment 6 can prepare a participant session package.
- [ ] `session_manifest.json` resolves under writable local validation/session
  paths.
- [ ] In multi-profile matrix runs, each prepared participant session package
  and session manifest stay under that profile's own validation session root,
  not a previous profile's remembered output folder.
- [ ] Session metadata carries profile/template identity and recreation
  provenance.
- [ ] The standalone runner profile selector exposes the profile only when it
  is ready.
- [ ] A fast fake-audio or emulated-response run can complete at least one
  prepared session for each ready profile before hardware Protocol 11 claims.
- [ ] Non-Study-5 profiles do not depend on Study-5-only assumptions.

### Reporting

- [ ] The matrix writes JSON and Markdown reports.
- [ ] Reports list ready profile count, blocked sample count, per-profile
  pass/fail, Segment 0-6 artifact paths, materialized totals, and blocker
  reasons.
- [ ] Reports explicitly state that this is toolkit parameter recreation, not
  physical timing or exact original-stimulus validation.

## Passing Rule

The protocol passes only when every tested ready published profile passes the
profile gate and Segment 0-6 materialization checks, and every blocked-profile
negative sample remains blocked with explicit reasons.
