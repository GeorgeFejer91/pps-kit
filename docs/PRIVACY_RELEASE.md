# Privacy And Release Checklist

Before publishing a release, run:

```powershell
python tools\release_audit.py
python tools\make_release_bundle.py
pytest
```

## Files Intended For Publication

- source code under `src\`
- Windows scripts under `windows\`
- reusable seed assets under `assets\`
- the bundled FABIAN/TU SOFA HRIR plus its attribution/hash manifest
- pinned third-party source snapshots under `third_party\`
- deidentified sample CSVs under `data\sample\`
- documentation, tests, and tool scripts

## Files Not Intended For Publication

- `local_data\`
- `artifacts\`
- `models\`
- `Example-configs\`
- raw loopback recordings
- participant demographics
- name-bearing decoder outputs
- third-party HRIR/SOFA files if their license does not permit redistribution
- licensed background music

## One-Bundle Archive

Use `python tools\make_release_bundle.py` to create a single reviewed zip for
distribution or repository upload. The generated zip contains a
`bundle_manifest.json` file with SHA256 hashes for every bundled file, including
the FABIAN SOFA asset and the pinned 3DTI source snapshot metadata.

## Data Handling

The runner defaults to local ignored paths for participant data. If a lab changes these paths, it should preserve the same separation between public repository files and participant-specific runtime files.
