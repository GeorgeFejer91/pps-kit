# Privacy Boundary

The public repository is a toolkit plus deidentified sample-data package. It is not a full study archive and should not contain participant recordings, participant names, demographics, generated participant stimuli, local settings, model downloads, or third-party assets whose redistribution status is not verified.

## Public By Design

- source code under `src/`
- tests under `tests/`
- small owned seed assets under `assets/breathing/`, `assets/click/`, and `assets/master_blocks/`
- deidentified sample CSVs under `data/sample/`
- example configs under `configs/`
- documentation under `docs/`
- citation and license metadata

## Local Or Generated Only

- generated stimuli and participant sequence WAVs: `artifacts/`
- loopback recordings and session outputs: `local_data/`
- Kokoro model downloads: `models/`
- user-supplied SOFA/HRIR files unless redistribution rights are verified
- background music or third-party sound libraries unless redistribution rights are verified

## Publication Check

Before publishing or pushing a release, run:

```powershell
python tools\release_audit.py
pytest
```

If the audit fails, remove the private or generated file from the public tree and rerun the check.
