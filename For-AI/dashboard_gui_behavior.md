# Dashboard GUI Behavior

## View/Edit Mode

The HTML dashboard has a single left-rail switch positioned between the visible labels `View` and `Edit`. A dynamic SVG lock sits above it: its shackle is closed in View and animates open only after Edit is actually available. Do not repeat the state with a `Mode` heading or a `view mode`/`edit mode` status chip. `View` is the safe default on page load, profile load, existing custom-study load, and refresh. In View mode, researchers can inspect, navigate, preview audio, open folders, launch already prepared profile-run actions, and save a prepared experiment as a reusable study profile, but mutation controls are locked.

Entering `Edit` on a bundled/read-only or finalized profile opens the custom-profile naming modal first; the lock must remain visually closed until that dialog creates the copy. The derived display name retains the immutable source profile ID. After the custom draft is created, the switch moves to Edit and the shackle animates open. A named draft can move between View and Edit without being copied again, and its inputs autosave while editable. Backend signature comparison invalidates downstream Segment artifacts from the earliest changed scientific segment. `Done — Lock Profile` returns the switch to View, animates the lock closed, and changes the profile to copy-to-edit-only; only finalized profiles enter the Runner catalogue.

Hosted composition can clone immutable profiles and edit browser-local decisions. It persists the draft and fixed local audio in IndexedDB, never uploads selected files, and can export `.pps-profile`. Hosted mode keeps trajectory mutation, looming generation/spatialization, workspace writes, and Runner actions disabled. Stored trajectories remain inspectable in 2D/3D.

The applet retains the long Segment 0-6 scroll surface, per-stage headings/actions, and collapse controls. Stage headings and action footers may remain sticky on wider layouts, but both are static in the phone flow so they cannot obscure scientific content or controls. The independently launched desktop applet omits the hosted page-navigation/status top bar entirely because its sidebar already owns the full `Peripersonal Space Design Toolkit` identity, mode, theme, and workflow navigation. Theme selection is a minimal horizontal sun/moon pill in the sidebar: a single high-contrast indicator sits behind the active line icon and slides between the two states. Do not use nested black/white squares or a text `Dark`/`Light` button. Public Documentation and Downloads navigation remains on the hosted website; the hosted interface uses the same sidebar theme toggle while retaining its page/status top bar. On hosted layouts at `760px` or narrower, the sticky page-tab bar is the first page surface above the stacked sidebar, with page navigation in a full-width first row, status controls below it, and short visible `Experiment`/`Docs` labels that retain full accessible names and do not clip.

All layout and styling changes follow `interface_design_principles.md`: a 4 px base/8 px primary rhythm, shared panel and control geometry, explicit alignment meridians, hierarchy-driven salience, WCAG-aware target/focus/reflow behavior, and iterative screenshot inspection after every visual change.

Read-only profile inspection remains fully legible. Do not dim entire read-only panels or repeat the global lock state with per-panel `inherited · read-only` or `finalized · locked` pills: the animated sidebar lock, disabled mutation controls, and pointer-event gating communicate capability while retaining normal content/surface contrast in both themes. Editable drafts retain per-step review badges because those describe workflow progress rather than profile editability. Themeable application cards and controls use semantic surface/color variables; white backgrounds are reserved for content that inherently needs a white canvas, such as a waveform image.

## Mobile Phone Layout And Interaction

At `760px` or narrower, the sidebar becomes a compact orientation and disclosure surface beneath the page tabs. The View/Edit lock state remains visible without repeating status text. The active page's workflow sections and `Local Companion` each use an explicit disclosure button and default collapsed; expanding one reveals its controls without forcing every phone visit through the entire rail. Page tabs retain proper tab semantics and keyboard operation, and the current workflow location remains identifiable while its section list is closed. The compact short-height treatment is landscape-only, so a short portrait viewport never acquires desktop-width top-bar columns or horizontal overflow.

Ordinary phone controls provide at least a 44 px touch target. Segment headings use one consistent reflow for segment identity, title, About, and Collapse/Expand actions; action footers are static and never overlay content. Panel resize handles are disabled at `760px` or narrower. Layouts must reflow without segment-local horizontal scrolling: dense Segment 5/6 tables become labeled record cards, and long block rows initially show a useful subset behind an explicit show-all/show-less control. Read-only phone views hide mutation-only add, remove, and reorder affordances while preserving complete scientific previews and view controls.

Phone dialogs are bounded by the viewport, scroll internally, trap keyboard focus, make the underlying application shell inert, support Escape, and return focus to their opener. Dark Documentation, Downloads, modal, and scientific-summary surfaces must derive foregrounds and backgrounds from semantic theme variables rather than retaining light-theme fixed colors.

Responsive verification covers at least 320 px and 390 px portrait widths, a short phone landscape viewport, both sides of the 760/761 px mobile-layout boundary, and 600/601 px continuity probes. It checks every Segment 0-6 surface in light and dark themes, page-tab and rail-disclosure interaction, 44 px targets including radio/checkbox labels, absence of overflow/overlap, labeled mobile table records and progressive row reveal, static phone footers/headings, hidden resize handles, modal focus containment, and post-interaction browser errors.

## Segment 0 Profile Chooser

Segment 0 is a parsimonious profile catalogue, not an acquisition or folder-configuration surface. It exposes one grouped `Profile` selector containing immutable built-in study templates and researcher-owned custom designs, one `Start New Custom Design` button, and one compact contextual profile card. The card begins with the stable profile ID and then shows citation, DOI, and optional source provenance. It does not repeat the selected profile title, template/read-only status, asset count, or recreation caveat. Custom profiles must not be duplicated in a second selector. The direct `Refresh`, `Apply Design`, `Apply Profile / Create Project Folder`, `Open Folder`, and data-acquisition-folder controls are not part of Segment 0.

Selecting a profile loads it for inspection without an additional Apply step. Starting a clean-slate design first requires a name and creates a draft in the fixed researcher workspace; desktop and hosted drafts then autosave. Attempted mutation of a built-in or finalized profile still opens the provenance-preserving copy-and-name dialog. The Segment 0 About modal calls the installed or hosted study-template source the `Template Directory`; the phrase is a link that opens the physical directory locally and the repository directory online. It also owns the published-profile recreation caveat, keeping that explanation out of the ordinary selection surface. Its fourth workflow heading is `Output`.

The profile selector and `Start New Custom Design` share an exact control height and vertical center on desktop layouts. Segment heading, panel content, chooser row, information card, and metadata share project grid meridians. The profile card uses a tokenized vertical flow, and its identity/provenance fields form a compact aligned metadata grid rather than unrelated floating text blocks.

DOI and other external HTTP(S)/mailto links remain ordinary new-tab links in hosted mode. In the native desktop applet, the shared frontend intercepts the click and calls the pywebview shell explicitly; Linux prefers `gio open` so registered desktop and Flatpak browsers resolve reliably, with `xdg-open` as a compatibility fallback. Windows uses the shell URL handler and macOS uses `open`, with Python's browser module as the final fallback. The embedded webview must not attempt to navigate to the external page itself.

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

Hosted/static mode cannot write WAVs or CSVs, but finished bundled profiles must still show the same downstream decisions that the local companion would materialize. `staticStateForTemplate()` therefore derives read-only virtual Segment 3 trial files, Segment 4 repetition-pool rows, and already-randomized Segment 5 block previews from the committed profile parameters. Canonical Study 5 should show 44 virtual Segment 3 WAVs, 204 planned Segment 4 pool rows, and 6 accepted static block previews of 34 trials each. The lateral DynaSpace Study 5 profile should show 52 virtual Segment 3 WAVs, 204 planned Segment 4 pool rows, and the same six 34-trial block previews. Static previews must use the same seeded, row-order-preserving Gellermann-style block scheduler concept as the local companion and expose `Download Randomization` for the browser-generated CSV/manifest. The local companion materializes Designer-owned WAV/CSV artifacts; the Experiment Runner later materializes participant sessions from finalized profiles.

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
