# Product Applet And Shared-Workspace Architecture

## Status

This document records the agreed product direction as of 2026-08-05. It is a
target architecture for release maturation, not a claim that every current
source module already follows these boundaries. Current implementation
ownership remains documented in `module_map.md` and `docs/ARCHITECTURE.md`.

## Product Shape

PPS Toolkit should present one central application hub with independently
runnable applets. The hub is a launcher, status, recent-work, documentation,
and settings surface; it must not become the authority for stimulus files,
manifest validity, participant timing, or runtime acquisition. Closing the hub
must not interrupt an applet that is already running.

The intended applet families are:

- Experiment Designer and Stimulus Generator
- native Windows Experiment Runner
- Android companion, with PC Runner Control and experimental phone-local
  execution kept visibly distinct
- Analysis and Review
- Calibration and Hardware tools
- internal Validation and Development tools, which are not routine participant
  runtime features

Each product applet should have its own interface/widgets and direct launcher.
Where useful, it should also expose a documented CLI or programmatic entry
point. An applet must not need another applet's GUI to perform its own work.

## Shared Core And Source Of Truth

The hub and applets should use one shared PPS core and researcher workspace.
They should exchange versioned domain objects through documented APIs and
schemas rather than importing private functions from another applet.

The shared ground truth includes:

- profile and template catalogues
- experiment-design schemas and accepted Segment manifests
- stimulus and imported-asset catalogues, hashes, and provenance
- trajectories, timing definitions, trial pools, accepted blocks, and
  participant schedules
- immutable prepared-experiment packages
- machine-scoped hardware/calibration records where applicable
- schema versions, migration metadata, and reproducibility hashes

The source of truth is not one large mutable state file. Authoritative objects
should remain separated, versioned, hashable, and validated. The current
Segment manifest chain is the starting implementation of this contract.

Browser JavaScript and the central hub remain request/display layers. Timing,
rendered files, manifest validity, and acquisition outputs remain owned by the
appropriate core or runtime authority.

## Required Independence And Handoffs

The following workflows are first-class product requirements:

1. Use the Designer/Stimulus Generator alone to create, render, inspect, and
   export stimuli without running an experiment in PPS Focus Mode.
2. Select a finished built-in study template and run it without manually
   redesigning it. The preparation layer may materialize its runnable package
   automatically.
3. Create a new custom protocol, prepare it, and hand the resulting package to
   the native runner.
4. Open the native runner directly with an already prepared session package.
5. Decode, review, or analyze compatible outputs without reopening the
   designer or runner.

The stable boundary between authoring and acquisition should be a portable,
versioned prepared-experiment package. Conceptually:

```text
profile or custom design
    -> shared preparation API
    -> immutable prepared experiment
    -> Windows runner, Android runner, validator, or archive
```

Dashboard, CLI, hub, and direct profile-launch routes should become clients of
the same public preparation API. In particular, the runner should not depend
long-term on private helpers inside `dashboard_app.py` to materialize profiles.

## Template And Profile Lifecycle

Use these terms consistently:

- **Built-in template**: an immutable, versioned study definition distributed
  with PPS Toolkit.
- **Custom profile**: a researcher-owned editable design created from scratch,
  from a built-in template, or from another custom profile.
- **Prepared experiment**: an immutable runnable snapshot created from a
  built-in template or custom profile.
- **Participant session**: one acquisition instance created from a prepared
  experiment.

### Built-in templates

Published-study and other package-supplied templates must never be edited in
place. They are read-only release resources with stable identifiers, version,
schema, citation/recreation status, asset provenance, and validation state.
They may be inspected, rendered, prepared, and run directly.

### Clone on edit

Attempting to change a built-in template must create a custom profile before
the change is applied. The preferred UI flow is read-only `View` followed by
`Customize`, with a clear clone-on-edit explanation. The original template
must remain untouched.

A derived custom profile must retain at least:

- its own stable profile id and display name
- `profile_kind = custom`
- source/parent profile id
- source/parent version and schema version
- source/parent content hash
- creation time and subsequent revision identity
- referenced or copied asset provenance

The package should use the name **custom profile**, not **custom template**, for
editable researcher-owned designs so canonical package templates remain
unambiguous.

### Preparation boundary

Editable custom profiles are drafts. Preparing a profile creates an immutable
experiment snapshot with exact assets and hashes, accepted blocks,
randomization seed/order, scientific runner settings, schema version, and
provenance. Later edits to the source custom profile must not change an
existing prepared experiment. A changed design requires a new prepared
revision so participants cannot silently receive different protocols under one
experiment identity.

## Storage Boundary

Keep the three storage roles distinct:

```text
application installation / release resources
    read-only built-in templates, schemas, standard assets, applets

researcher workspace
    editable custom profiles, imported assets, generated stimuli,
    immutable prepared experiments, machine calibration records

participant acquisition outputs
    local session data, recordings, events, markers, analysis outputs
```

Application upgrades may add a new version of a built-in template but must not
rewrite custom profiles derived from an older version. Provenance must keep the
older source version and hash reconstructable. Participant data remains outside
Git and outside the reusable profile catalogue.

## Release Direction

This modular applet/shared-core architecture is the product direction for
maturing PPS Toolkit component by component toward a public scientific-software
release, including a possible JOSS paper in addition to the existing Behavior
Research Methods manuscript direction. Modularity does not require separate
repositories or installers initially: the first priority is stable public
schemas, explicit APIs, independent launch paths, examples, tests, and clear
evidence boundaries.

## Implemented Designer Boundary (2026-08-05)

The first applet implementation is now `pps-designer`. It starts the existing
FastAPI service on loopback and hosts the compiled Vite frontend in a native
`pywebview` window: WebView2 on Windows and GTK/WebKitGTK on Linux. Bare
`pps-dashboard` is a one-release compatibility alias; explicit
`pps-dashboard --no-browser` remains the companion/testing service.

GitHub Pages and the native shell consume `dashboard/compiled/`, generated
from the adjacent HTML/CSS/ES-module source. Hosted composition stores drafts
and selected fixed audio in IndexedDB and exports `.pps-profile` without
uploading files. It cannot render looming audio, change trajectories, write
workspace folders, or launch the Runner.

`.pps-profile` is a ZIP-compatible `pps-profile-bundle.v1` with canonical
profile JSON, stored trajectory provenance, content-addressed audio, and a
SHA-256 inventory. The Python importer rejects unsafe paths, missing or
uninventoried files, hash/size mismatches, duplicate logical IDs, unsupported
schemas, and binary substitutions disguised as audio.

Custom profiles have a draft/finalized lifecycle. Editing an immutable
template or finalized profile creates a named copy whose display name retains
the source profile ID. Draft decisions autosave and scientific changes
invalidate downstream Segment artifacts. `Done — Lock Profile` finalizes the
profile and makes it copy-to-edit-only. The Runner catalogue excludes drafts
and can materialize the legacy Segment 6 session/order artifact on demand from
a finalized Segment 0-5 profile.
