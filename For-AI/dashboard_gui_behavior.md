# Dashboard GUI Behavior

## View/Edit Mode

The HTML dashboard has a single left-rail switch positioned between the visible labels `View` and `Edit`. A dynamic SVG lock sits above it: its shackle is closed in View and animates open only after Edit is actually available. Do not repeat the state with a `Mode` heading or a `view mode`/`edit mode` status chip. `View` is the safe default on page load, profile load, existing custom-study load, and refresh. In View mode, researchers can inspect, navigate, preview audio, open folders, launch already prepared profile-run actions, and save a prepared experiment as a reusable study profile, but mutation controls are locked.

Entering `Edit` on a bundled/read-only or finalized profile opens the custom-profile naming modal first; the lock must remain visually closed until that dialog creates the copy. The derived display name retains the immutable source profile ID. After the custom draft is created, the switch moves to Edit and the shackle animates open. Edit mode exposes exactly one decision segment at a time: the active segment is editable, earlier saved segments are read-only, and downstream segments stay visible but are lightly muted and read-only. Inputs do not autosave. Segments 1-4 use explicit `Save & Continue` actions, Segment 5 uses `Accept Blocks & Continue`, and only those confirmation boundaries advance the persisted edit cursor. Sequential step footers show only the active forward action; disabled utility-only footers disappear until View mode restores the full overview. Artifact bakes may make a segment operationally valid but must not advance that cursor on their own. `Done — Lock Profile` returns the switch to View, animates the lock closed, and changes the profile to copy-to-edit-only; only finalized profiles enter the Runner catalogue.

The persisted `designer_progress` record is separate from artifact validity: `custom_workflow.current_step` remains the first operationally incomplete segment, while `custom_workflow.edit_step`, `confirmed_steps`, `needs_review_steps`, and `review_revision` describe sequential review. A completed earlier segment exposes `Reopen segment`; reopening truncates later confirmations and marks previously saved downstream decisions for review without hiding their values. A stale or out-of-order save is rejected. Segment 5 acceptance and cursor advancement are one atomic, retry-safe backend action. Finalization requires the current revision, the Segment 6 cursor, confirmations for Segments 0-5, and no review debt; `profile_status` and `finalized_at` are server-owned. Unsaved edits set the global save indicator to `unsaved`, remain local while typing, trigger a browser-leave warning, and require explicit discard confirmation before returning to View, reconnecting, or loading another profile.

Only the active segment shows its forward confirmation control. Saved, downstream, and View-mode segments do not repeat disabled `Save & Continue`, `Accept Blocks & Continue`, or final-lock calls to action; this keeps the overview focused on decisions rather than unavailable actions.

Hosted composition can clone immutable profiles and edit browser-local decisions. It persists the draft and fixed local audio in IndexedDB, never uploads selected files, and can export `.pps-profile`. Hosted mode keeps trajectory mutation, looming generation/spatialization, workspace writes, and Runner actions disabled. Stored trajectories remain inspectable in 2D/3D.

The applet retains the long Segment 0-6 scroll surface, per-stage headings/actions, and collapse controls. Stage headings and action footers may remain sticky on wider layouts, but both are static in the phone flow so they cannot obscure scientific content or controls. The independently launched desktop applet omits the hosted page-navigation/status top bar entirely because its sidebar already owns the full `Peripersonal Space Design Toolkit` identity, mode, theme, and workflow navigation. Theme selection is a minimal horizontal sun/moon pill in the sidebar: a single high-contrast indicator sits behind the active line icon and slides between the two states. Do not use nested black/white squares or a text `Dark`/`Light` button. Public Documentation and Downloads navigation remains on the hosted website; the hosted interface uses the same sidebar theme toggle while retaining its page/status top bar. On hosted layouts at `760px` or narrower, the sticky page-tab bar is the first page surface above the stacked sidebar, with page navigation in a full-width first row, status controls below it, and short visible `Experiment`/`Docs` labels that retain full accessible names and do not clip.

All layout and styling changes follow `interface_design_principles.md`: a 4 px base/8 px primary rhythm, shared panel and control geometry, explicit alignment meridians, hierarchy-driven salience, WCAG-aware target/focus/reflow behavior, and iterative screenshot inspection after every visual change.

## Documentation Typography

The opening `What Is Peripersonal Space` section uses `@chenglou/pretext` for bounded text fitting while preserving ordinary semantic HTML, links, selection, and accessibility. After named fonts are ready, the lead is fitted to a six-line desktop budget and the canonical-measure paragraph is fitted against the media column's available height; a width observer recalculates those values without DOM measurement loops. Sizes remain within declared readable minimum/maximum bounds, and any unsupported or failed measurement removes the computed values so CSS typography remains a complete fallback.

The opening media/copy composition must never stretch the embedded video. It preserves a 16:9 frame, uses a labeled figure/caption and a distinct canonical-measure text group, and switches to one column when the section container reaches 780 px or narrower. The documentation canvas may be wider than ordinary prose, but later body copy remains line-length constrained. Packaged/local and hosted/static dashboards use the same compiled module and pinned dependency.

Read-only profile inspection remains fully legible. View mode always restores the complete, unmuted Segment 0-6 overview; no workflow segment is hidden or gray merely because the profile is finished or the draft is being inspected. Do not dim entire read-only panels or repeat the global lock state with per-panel `inherited · read-only` or `finalized · locked` pills: the animated sidebar lock, disabled mutation controls, and pointer-event gating communicate capability while retaining normal content/surface contrast in both themes. Only downstream segments in sequential Edit mode receive the subtle muted treatment. Editable drafts retain per-step review badges because those describe workflow progress rather than profile editability. Themeable application cards and controls use semantic surface/color variables; white backgrounds are reserved for content that inherently needs a white canvas, such as a waveform image.

## Mobile Phone Layout And Interaction

At `760px` or narrower, the sidebar becomes a compact orientation and disclosure surface beneath the page tabs. The View/Edit lock state remains visible without repeating status text. The active page's workflow sections and `Local Companion` each use an explicit disclosure button and default collapsed; expanding one reveals its controls without forcing every phone visit through the entire rail. Page tabs retain proper tab semantics and keyboard operation, and the current workflow location remains identifiable while its section list is closed. The compact short-height treatment is landscape-only, so a short portrait viewport never acquires desktop-width top-bar columns or horizontal overflow.

Ordinary phone controls provide at least a 44 px touch target. Segment headings use one consistent reflow for segment identity, title, About, and Collapse/Expand actions; action footers are static and never overlay content. Panel resize handles are disabled at `760px` or narrower. Layouts must reflow without segment-local horizontal scrolling: dense Segment 5/6 tables become labeled record cards, and long block rows initially show a useful subset behind an explicit show-all/show-less control. Read-only phone views hide mutation-only add, remove, and reorder affordances while preserving complete scientific previews and view controls.

Phone dialogs are bounded by the viewport, scroll internally, trap keyboard focus, make the underlying application shell inert, support Escape, and return focus to their opener. Dark Documentation, Downloads, modal, and scientific-summary surfaces must derive foregrounds and backgrounds from semantic theme variables rather than retaining light-theme fixed colors.

Responsive verification covers at least 320 px and 390 px portrait widths, a short phone landscape viewport, both sides of the 760/761 px mobile-layout boundary, and 600/601 px continuity probes. It checks every Segment 0-6 surface in light and dark themes, page-tab and rail-disclosure interaction, 44 px targets including radio/checkbox labels, absence of overflow/overlap, labeled mobile table records and progressive row reveal, static phone footers/headings, hidden resize handles, modal focus containment, and post-interaction browser errors.

## Documentation Publication Network

The Documentation page contains one focused audio–tactile PPS publication and citation network. Its v3 projection contains 94 non-review publications: 90 manually confirmed by the original audio-tactile corpus audit plus 4 later exact-DOI Toolkit-audit additions. Candidate scope is then gated by a canonical DOI-keyed `https://doi.org/` link confirmed by the dated exact-DOI resolver audit and provider-backed citation metadata; a finite zero count is valid available metadata. Papers missing either requirement are excluded. Toolkit readiness never determines inclusion. The broad 1,712-publication snapshot remains provenance input rather than a user-facing filterable corpus.

The graph uses a responsive square surface in both source/local and compiled/hosted dashboards at desktop and phone widths. `Citation topology` is the default deterministic density-preserving force layout: citation neighbours attract, every paper participates in the same repulsion and weak-centering forces, and radius-aware separation prevents overlap. The declared normalized node clearance is `0.015`. The 91-node main component spans most of the map without erasing genuine density differences; the 3 records with no verified within-map link are not forced onto a perimeter. Circle area encodes only normalized incoming citations from other papers in the displayed 94-paper network, using a monotonic log-area scale with radii from `0.009` to `0.024`; external citation totals, broad-corpus counts, PageRank, and prominence do not determine circle size. `Publication year` is the alternative continuous year-anchored layout and remains collision-free.

The network plot is an inline SVG, not a raster canvas. Nodes, edges, selected-direction arrowheads, selection rings, and year guides use the same semantic `--network-*` CSS variables as the visible legend. A `data-theme` change therefore recolors the page, legend, and every graph mark in the same browser style update without a JavaScript repaint race. Preserve the SVG renderer and its separate semantic publication list when changing graph interaction or styling.

All 750 tracked directed links between eligible publications are always visible: 571 from the frozen multi-source snapshot, 127 non-overlapping links from the exact-DOI OpenAlex overlay captured 2026-08-08, and 52 retained links from the 60-link primary-reference audit after excluding DOI-less endpoints. The compact toolbar has only the topology/year arrangement choice; there is no paper-search or citation-link control. Selecting a node distinguishes incoming from outgoing citation direction. The map legend has only two implementation states, 15 implemented and 79 not implemented yet; the detail panel preserves the full four-state evidence assessment of 15 runnable, 49 supported but parameter-incomplete, 29 not assessed, and 1 adjacent/scope conflict. Details show title, authors, DOI/source links, abstract provenance or availability caveat, metrics, directional citation neighbours, and every exact-DOI Toolkit record and extracted parameter. The semantic publication list, keyboard navigation, focus return, live status, dark theme, and reduced-motion/mobile behavior remain equivalent accessible inspection paths; citation size and centrality are navigation encodings, never study-quality measures.

## Segment 0 Profile Chooser

Segment 0 is a parsimonious profile catalogue, not an acquisition or folder-configuration surface. It exposes one grouped `Profile` selector containing immutable built-in study templates and researcher-owned custom designs, one `Start New Custom Design` button, and one compact contextual profile card. The card begins with the stable profile ID and then shows citation, DOI, and optional source provenance. It does not repeat the selected profile title, template/read-only status, asset count, or recreation caveat. Custom profiles must not be duplicated in a second selector. The direct `Refresh`, `Apply Design`, `Apply Profile / Create Project Folder`, `Open Folder`, and data-acquisition-folder controls are not part of Segment 0.

Selecting a profile loads it for inspection without an additional Apply step. Starting a clean-slate design first requires a name and creates a draft in the fixed researcher workspace; desktop and hosted drafts persist at explicit segment actions rather than while the researcher types. Attempted mutation of a built-in or finalized profile still opens the provenance-preserving copy-and-name dialog. The Segment 0 About modal calls the installed or hosted study-template source the `Template Directory`; the phrase is a link that opens the physical directory locally and the repository directory online. It also owns the published-profile recreation caveat, keeping that explanation out of the ordinary selection surface. Its fourth workflow heading is `Output`.

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

## Final-Segment Randomization Seed

Segments 4-6 use one explicit non-negative 31-bit randomization seed. Segment 5
shows the persisted seed beside block count, accepts researcher-entered values,
and offers `New Seed` using the browser cryptographic random source, which works
without network access. `Generate Blocks` and `Regenerate Blocks` reuse the
visible value; they must never silently replace it. The seed is saved as
`protocol.random_seed`, controls Segment 4 fractional balancing and Segment 5
row-preserving block assignment, and is copied into the Segment 6 participant
order policy/run manifest. Seed `0` is valid and must not trigger default-value
fallbacks. The same seed and inputs must produce the same order in hosted/static
preview JavaScript, the local companion backend, and packaged desktop webviews.

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

Hosted/static no-companion mode must keep every profile visible in the static selector aligned with committed offline/local profile truth. Ready launchable profiles must match local dashboard preview counts and read-only Segment 3-6 summaries; blocked profiles must remain inspectable only as metadata/source/trajectory/blocker previews and must not appear launchable. Browser-local copy-on-edit, composition, IndexedDB draft/audio storage, finalization, and portable profile export remain available without a companion. Rendering/baking, workspace or acquisition-folder writes, local-folder opening, and runner launch remain disabled until the hosted page connects to the local companion.

Static profile hydration must consume every committed preload asset, not only the first source card stored in the template JSON. Direction-expanded inventories such as front/back, left/right, looming/receding, or spherical boundary profiles should append unconsumed assets as read-only preserved custom sources, expand Segment 2 `looming_stimulus` source labels to the concrete asset labels, and use the source trajectory as the direction factor when multiple asset direction labels are present. Static defaults should mirror backend profile-load defaults: catch trials are inferred from explicit counts/percentages, tactile-only and stationary-burst baselines span the full SOA list, and launchability remains controlled by the profile recreation ledger rather than static preview synthesis.

`validation_protocols/scripts/run_static_dashboard_preview_parity_audit.py` is the static-preview parity harness. It can force the dashboard into no-companion static mode with `forceStaticPreview=1`, read the query-gated sanitized browser snapshot exposed by `auditStaticPreview=1`, and compare all static-selectable profiles against preload/profile ledgers plus local Protocol 12 materialization for ready profiles. The audit surface must stay validation-only and must not expose local paths, participant data, generated outputs, or secrets.
