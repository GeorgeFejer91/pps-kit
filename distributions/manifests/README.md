# PPS component manifests

The V1 files implement `pps-component-manifest.v1` for the Python compatibility
distribution. The V2 files implement `pps-component-manifest.v2` for the Tauri
Windows Full installer. A component
manifest names its compatible component version, install mappings, dependencies,
entry points, platform, license references, and exclusions.

`shared` owns common resources and documentation. `designer` and `runner` own
their independent generated application trees and each requires the exact Shared
version declared in its manifest. `full` is composition-only: it installs one
copy of Shared and the two applications, with separate shortcuts and no hub.

V2 uses `planner` for the Tauri Planner application. The Planner worker is built
without embedded Shared resources in a Full package; its Rust parent locates
the single installed `shared/` tree. Runner keeps its own bundled web bytes.
`package_inventory.py --manifest-version v2 --strict` compares installed files
and trees byte for byte with the exact source build inputs.

Bootstrapper manifests pin the payload SHA-256 and component-inventory SHA-256.
An existing installation with a different Shared version must be rejected rather
than merged.
