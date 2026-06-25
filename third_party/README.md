# Third-Party Source Snapshots

This folder stores source snapshots or pinned fetch metadata for renderer
dependencies that are part of the reproducible experiment software stack.

## 3DTI AudioToolkit

`3dti_AudioToolkit/` is a source snapshot from
`https://github.com/3DTune-In/3dti_AudioToolkit` pinned at commit
`6bfee08705675308a8c348b4c3a4d582586d2f99`.

Only source, docs, and license/build-relevant files are vendored here. The
upstream `resources/` folder is intentionally excluded because it contains
sample audio and HRTF/BRIR resources that should not be redistributed as part
of this toolkit unless their licenses are separately reviewed.

The 3DTI snapshot is accompanied by its pinned submodule contents because the
native renderer must build offline from the release bundle:

- `3dti_ResourceManager/third_party_libraries/cereal/` at
  `51cbda5f30e56c801c07fe3d3aba5d7fb9e6cca4`
- `3dti_ResourceManager/third_party_libraries/eigen/` at
  `a1b9c26c5e62cb8c17836e601edd64b92aa8e5ae`
- `3dti_ResourceManager/third_party_libraries/sofacoustics/` at
  `2c5c3e269f66f5d6854bb9941937d43f8578fd04`

The SOFA API snapshot includes Windows x64 NetCDF/HDF5/Curl/Zlib runtime
libraries used by the native wrapper build.

## nlohmann/json

`nlohmann_json/` contains a pinned MIT-licensed single-header copy of
nlohmann/json v3.11.3 for the native `pps-3dti-renderer` wrapper. The pin file
records the exact upstream version and hashes.
