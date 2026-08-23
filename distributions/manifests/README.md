# PPS component manifests

The four versioned JSON files implement `pps-component-manifest.v1`. A component
manifest names its compatible component version, install mappings, dependencies,
entry points, platform, license references, and exclusions.

`shared` owns common resources and documentation. `designer` and `runner` own
their independent generated application trees and each requires the exact Shared
version declared in its manifest. `full` is composition-only: it installs one
copy of Shared and the two applications, with separate shortcuts and no hub.

Bootstrapper manifests pin the payload SHA-256 and component-inventory SHA-256.
An existing installation with a different Shared version must be rejected rather
than merged.
