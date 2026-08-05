# Dashboard GUI Behavior

## View/Edit Mode

The HTML dashboard has a left-rail `View / Edit` mode switch. `View` is the safe default on page load, profile load, existing custom-study load, and refresh. In View mode, researchers can inspect, navigate, preview audio, open folders, launch already prepared profile-run actions, and save a prepared experiment as a reusable study profile, but mutation controls are locked.

Entering `Edit` on a bundled/read-only or finalized profile opens the custom-profile naming modal first. The derived display name retains the immutable source profile ID. After the custom draft is created, Edit mode unlocks applicable decisions. Draft inputs autosave. Backend signature comparison invalidates downstream Segment artifacts from the earliest changed scientific segment. `Done — Lock Profile` changes the profile to copy-to-edit-only; only finalized profiles enter the Runner catalogue.

Hosted composition can clone immutable profiles and edit browser-local decisions. It persists the draft and fixed local audio in IndexedDB, never uploads selected files, and can export `.pps-profile`. Hosted mode keeps trajectory mutation, looming generation/spatialization, workspace writes, and Runner actions disabled. Stored trajectories remain inspectable in 2D/3D.

The applet retains the long Segment 0-6 scroll surface. Fixed chrome shows capability and saved/unsaved state, a persistent light/dark theme, contextual Help, sticky stage headings/actions, and per-stage collapse controls. Desktop applet mode hides public Documentation and Downloads tabs; those remain on the public website.

## Trajectory Preview

The Segment 1 trajectory preview is an embedded Three.js viewer that is lazy-loaded as it approaches the viewport. The right-side preview controls (`2D`, `3D`, view presets, zoom, fit radius, reset) are view-only camera controls and must stay usable in read-only, locked, and hosted/static modes. The left trajectory/source controls remain mutation controls and are gated by View/Edit mode.

The dashboard must not depend solely on catching the iframe `load` event before it sends preview payloads. If the viewer iframe loads before listeners are attached, `updateViewer()` should detect the viewer API when it becomes available, mark it ready, and push the current payload so online/static previews do not remain stuck on the viewer's initial placeholder 2D scene.

## Downward Source Propagation

Top-level source-card labels are parent decisions for Segment 2 trial-sequence audio boxes. When a source card is removed in Edit mode, that label is pruned immediately from every downstream sequence box before save. When a source-card label changes, existing downstream labels are renamed to the new label. Future label pickers are rebuilt from the current source pool.

The backend also prunes stale custom-design `trial_strips[*].elements[*].source_labels` during save, so direct/API payloads cannot persist labels for deleted sources. Bundled profile preloads remain unchanged and read-only until copied.

## Study 5 Bundled Profiles

The tracked preload `study5_box_breathing_pps` remains the first/default Study 5 lab profile in the repository. Its stable ID is retained for compatibility, and its source pool is the canonical white/pink version: exactly `Pink frontal` and `White frontal` salient looming burst sources plus `Inhale instruction` and `Exhale instruction` fixed clips from the original Study 5 audio. The profile retains the Study 5 SOAs, trajectory, instruction audio, stationary-burst baseline/catch settings, block/run defaults, and total trial-budget logic. Segment 3 baselines use `baseline_strategy = stationary_burst`: fixed instruction/jitter audio stays in place, looming segments are replaced by stationary rendered burst audio, and tactile cues remain on channel 3 at every main SOA. Because the looming source pool has two noises, Segment 4 family repetitions are scaled to audio-tactile `6.0`, baseline `3.0`, and catch `6.0`; this preserves 204 planned rows and six 34-trial blocks.

The approved second Study 5 profile is `study5_dynaspace_lateral_45_pps`. It keeps the original Study 5 breathing clips and run-instruction workflow, but replaces the frontal white/pink looming pool with two DynaSpace/Hobeika-style white-noise burst-train sources: `DynaSpace looming left 45` and `DynaSpace looming right 45`. These source cards carry their own trajectory snapshots: 640 cm to 20 cm, 3.85 s total, 0.105 s pre-hold, 2.945 s movement, 0.8 s post-hold, six smartphone anchors at SOAs `105, 1625, 2385, 2765, 2955, 3050` ms, and left/right display rotations 315 and 45 degrees. Segment 3 still uses stationary-burst baselines, now fixed at the matching left/right source snapshots. Segment 4 repetitions are audio-tactile `5.0`, baseline `2.5`, and catch `6.0`, producing 204 planned rows with equal inhale/exhale and left/right counts.

In the HTML dashboard study selector, `study5_box_breathing_pps` should appear as the first/default bundled Study 5 profile, and `study5_dynaspace_lateral_45_pps` should remain available as the lateral DynaSpace Study 5 variant.

## Segment 1 Generated Source Mode

Segment 1 `Generate Looming Noise` now has a visual `Source mode` widget pair
using the bundled waveform SVGs. `Burst train` is the default and writes
`source_profile: dynaspace_gaussian_burst_train`; `Smooth linear` writes
`source_profile: continuous_noise` as an explicit non-burst option. The browser
records only the researcher decision. The local backend validates the two
supported modes, normalizes burst-train parameters, clears stale burst
parameters for smooth-linear bakes, and then owns WAV generation.

Noise type is selected through visible quick-pick buttons rather than a dropdown:
White and Pink are the primary publication-backed choices, while Blue, Violet,
and Brown are smaller spectral variants with hover caveats. The legacy
`generated-noise-select` remains hidden as a JavaScript state mirror so existing
render/reset hooks keep working.

Existing generated source cards display a compact `Burst train` or
`Smooth linear` chip and keep the saved `source_profile`,
`source_profile_parameters`, and `motion_mode` fields in hidden form state.
Missing generated looming source profiles should resolve to `Burst train` when
designs are loaded/saved/rendered, while imported/fixed custom clips remain
outside this generated-noise toggle.

## Static Profile Segment 3-5 Previews

Hosted/static mode cannot write WAVs or CSVs, but finished bundled profiles must still show the same downstream decisions that the local companion would materialize. `staticStateForTemplate()` therefore derives read-only virtual Segment 3 trial files, Segment 4 repetition-pool rows, and already-randomized Segment 5 block previews from the committed profile parameters. Canonical Study 5 should show 44 virtual Segment 3 WAVs, 204 planned Segment 4 pool rows, and 6 accepted static block previews of 34 trials each. The lateral DynaSpace Study 5 profile should show 52 virtual Segment 3 WAVs, 204 planned Segment 4 pool rows, and the same six 34-trial block previews. Static previews must use the same seeded, row-order-preserving Gellermann-style block scheduler concept as the local companion and expose `Download Randomization` for the browser-generated CSV/manifest. The local companion still performs actual file/CSV materialization when launching or preparing a run.

The local companion must also serve the committed public static asset roots at
`/assets` and `/study_templates`. Connected read-only profile inspection uses
the same `staticStateForTemplate()` overlay as hosted/static mode, so these
routes must stay mounted alongside `/dashboard`, `/viewer`, and `/api/*`.

## Auditory-Only Response Trials

`Auditory-Only` is a first-class response-required trial family, separate from
no-response `Catch` rows. The browser static preview, backend Segment 3 bake,
Segment 4/5 pool counts, and Segment 6 manifests must count `auditory_only`
separately from `catch`. Its WAVs are stereo audio-only files with no tactile
channel, but the runner anchors response scoring to the response-window onset
and expects a mouse/response input when the row declares `expected_response =
respond`. Legacy `audio_only` labels still map to catch unless the profile uses
the explicit `auditory_only` / `Auditory-Only` family.

## Static Preview Parity Audit

Hosted/static no-companion mode must keep every profile visible in the static selector aligned with committed offline/local profile truth. Ready launchable profiles must match local dashboard preview counts and read-only Segment 3-6 summaries; blocked profiles must remain inspectable only as metadata/source/trajectory/blocker previews and must not appear launchable. Editing, baking, file import, saving, output-folder export, local-folder opening, and runner launch remain disabled until the hosted page connects to the local companion.

Static profile hydration must consume every committed preload asset, not only the first source card stored in the template JSON. Direction-expanded inventories such as front/back, left/right, looming/receding, or spherical boundary profiles should append unconsumed assets as read-only preserved custom sources, expand Segment 2 `looming_stimulus` source labels to the concrete asset labels, and use the source trajectory as the direction factor when multiple asset direction labels are present. Static defaults should mirror backend profile-load defaults: catch trials are inferred from explicit counts/percentages, tactile-only and stationary-burst baselines span the full SOA list, and launchability remains controlled by the profile recreation ledger rather than static preview synthesis.

`validation_protocols/scripts/run_static_dashboard_preview_parity_audit.py` is the static-preview parity harness. It can force the dashboard into no-companion static mode with `forceStaticPreview=1`, read the query-gated sanitized browser snapshot exposed by `auditStaticPreview=1`, and compare all static-selectable profiles against preload/profile ledgers plus local Protocol 12 materialization for ready profiles. The audit surface must stay validation-only and must not expose local paths, participant data, generated outputs, or secrets.
