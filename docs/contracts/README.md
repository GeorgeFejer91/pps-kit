# JSON handoff catalog

[`catalog.v1.json`](catalog.v1.json) indexes the versioned JSON contracts that
cross the Planner, Runner, controller, installer, or result-validation boundary.
Each entry points to its existing owner. The catalog is an index, not a
replacement validator or a second schema definition. Follow the owner when
changing fields, validation, or compatibility behavior. Update this catalog if
the contract identity or boundary changes. Internal segment and evidence
schemas stay with their owning modules.

The current component inventory remains in
[`distributions/manifests/`](../../distributions/manifests/README.md). Those
manifests describe the V1 package layout; a two-app Tauri Full installer will
need a versioned manifest update and installed-path audit.
