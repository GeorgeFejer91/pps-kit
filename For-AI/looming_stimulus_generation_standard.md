# Looming Stimulus Generation Standard

Date adopted: 2026-06-29.

This is the current PPS-kit operating standard for newly generated looming
stimuli and custom-study stimulus bakes.

## Core Decision

Use the DynaSpace/Hobeika burst-train source profile for source salience, but
keep spatial rendering in PPS-kit/3DTI/SOFA.

The standard is source-renderer separation:

- Dry source: broadband Gaussian white-noise burst train.
- Spatial renderer: 3DTI/SOFA or the Python SOFA/FABIAN reference path for
  preview/proxy assets.
- Metadata: every generated stimulus should declare source profile, trajectory,
  level policy, HRTF/SOFA resource, and QC outputs.

## Default Source Profile

Profile id: `dynaspace_gaussian_burst_train`.

Default parameters:

- `burst_count_mode`: `duration_derived`
- `burst_duration_s`: 0.030
- `rise_fall_s`: 0.010
- `target_period_s`: 0.095
- `onset_s`: 0.300
- `active_window_source`: `trajectory_movement_duration`
- `spacing_policy`: `symmetric_fit`

The default does not hard-code a universal burst count. It derives the count
from the configured active window and target period, then refits the actual
burst spacing so the first and final burst sit symmetrically inside the active
window. This avoids a clipped final burst when a trajectory duration is not an
exact multiple of the target period.

Evidence basis:

- Raw DynaSpace Android WAV audit found 33 bursts with about 95 ms median
  inter-onset interval for the smartphone profile's active burst window.
- Hobeika/DynaSpace lineage supports Gaussian white-noise bursts with short
  rise/fall ramps and about 95 ms burst onset spacing.
- Consensus searches supported broadband transients/onsets for salience and
  localization, and supported HRTF/ILD/ITD/reverb/near-field cues as spatial
  renderer properties rather than dry-waveform hacks.

## Renderer-Owned Spatial Features

Do not bake these into a static dry waveform when PPS-kit can model them:

- HRTF spectral filtering
- interaural level difference
- interaural time difference
- near-field behavior
- distance attenuation and propagation delay
- approach azimuth/elevation and future trajectory variants
- optional room, BRIR, reverberation, direct-to-reverberant ratio, and IACC

FABIAN/SOFA remains the redistributable default HRTF resource. Native 3DTI is
the renderer-of-record target for publication-grade spatial stimuli. The Python
SOFA/FABIAN renderer is a preview/proxy path and should be described that way.

## Applicability

Apply this standard to newly generated PPS-kit looming stimuli and dashboard
generated-noise bakes.

As of 2026-06-29, this is system-wide behavior for generated looming sources:

- missing generated-noise `source_profile` values are normalized to
  `dynaspace_gaussian_burst_train` when designs are loaded, saved, rendered, or
  exported into source/preload manifests
- explicit `source_profile: "continuous_noise"` is the only supported
  continuous-noise opt-out for generated sources
- Segment 1 exposes this choice as a `Source mode` segmented control, with
  `Burst train` selected by default and `Continuous` available for deliberate
  control/legacy bakes
- preload catalog rebuilds should regenerate generated-noise WAVs and QC rows
  after renderer/default-source-profile changes so bundled profiles match the
  current toolkit standard

Published-study recreations may override the default only when the original
paper or verified source material specifies a different waveform, apparatus, or
control logic. Any override must be explicit in the study template metadata and
should explain why it is a study-specific exception rather than the toolkit
default.

The raw DynaSpace Android WAVs are audit targets and provenance references, not
redistributable public assets.

## Controls And QC

Future generated profiles should support both:

- replication-like high-salience looming/fixed contrasts
- matched-level causal controls that separate spatial proximity from raw
  loudness/salience

Every generated looming WAV should record or export:

- no-clipping status
- peak/RMS or calibrated SPL policy
- source profile and parameters
- resolved burst count, active window, target period, and actual median
  inter-onset interval
- trajectory anchors and source position at tactile events
- HRTF/SOFA resource identity
- expected ILD/ITD/channel-sign direction for the requested azimuth
- IACC/DRR/reverb metrics when a room/externalization layer is enabled

See `docs/dynaspace_spectral_feature_audit/` for the source audit, Consensus
search export, implementation rationale, and generated PDF report.
