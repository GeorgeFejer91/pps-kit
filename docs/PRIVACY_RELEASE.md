# Privacy And Release Checklist

Before publishing a release, run:

```powershell
python tools\release_audit.py
pytest
```

## Files Intended For Publication

- source code under `src\`
- Windows scripts under `windows\`
- reusable seed assets under `assets\`
- deidentified sample CSVs under `data\sample\`
- documentation, tests, and tool scripts

## Files Not Intended For Publication

- `local_data\`
- `artifacts\`
- `models\`
- raw loopback recordings
- participant demographics
- name-bearing decoder outputs
- third-party HRIR/SOFA files if their license does not permit redistribution
- licensed background music

## Data Handling

The runner defaults to local ignored paths for participant data. If a lab changes these paths, it should preserve the same separation between public repository files and participant-specific runtime files.
