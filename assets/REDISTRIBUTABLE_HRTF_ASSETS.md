# Redistributable HRTF Assets

This project keeps the experimenter GUI free of raw SOFA/HRTF selection. Study
profiles preload trajectory, timing, and noise parameters; HRTF resources remain
standardized renderer assets under the hood. Generated noise and vibrotactile
cue waveforms are procedural and do not require bundled third-party audio clips.

## Standard Under-The-Hood Resource

### FABIAN neutral HRIR

- Intended role: fixed standardized mannequin/listener HRTF for PPS trajectory rendering
- File: `FABIAN_HRIR_measured_HATO_0.sofa`
- Expected local path: `assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa`
- Bundled SHA256: `83ebbcd9a09d17679b95d201c9775438c0bb1199d565c3fc7a25448a905cdc3c`
- Source record: https://depositonce.tu-berlin.de/items/3b423df7-a764-4ce1-9065-4e6034bba759
- SOFA mirror: https://sofacoustics.org/data/database/tu-berlin/
- License: CC BY 4.0, according to the DepositOnce record
- Bundle status: bundled standard resource; include attribution and hash manifest
- Refresh helper: `windows/Fetch_FABIAN_HRTF.ps1`

## Future QA Candidates

### HUTUBS single-subject HRIRs

- Intended role: optional alternative HRTF subjects for developer QA or future comparison, not a visible study-profile choice
- Example file: `pp1_HRIRs_measured.sofa`
- Source: https://sofacoustics.org/data/database/hutubs/
- Documentation: https://sofacoustics.org/data/database/hutubs/Documentation.pdf
- License: CC BY 4.0, according to the HUTUBS documentation
- Bundle status: approved candidate; choose a small subset only

### CIPIC SOFA subjects

- Intended role: optional public research reference set for developer QA or future comparison, not a visible study-profile choice
- Example file: `subject_003.sofa`
- Source: https://sofacoustics.org/data/database/cipic/
- Source paper: https://escholarship.org/uc/item/3d10j9jw
- License/provenance note: CIPIC is described as public-domain in the original
  paper/announcements; retain attribution and source notes because the original
  UC Davis hosting is no longer the most stable distribution point.
- Bundle status: optional candidate; review before including in a release bundle

## Excluded For Now

The upstream 3DTI `resources/` folder is intentionally not vendored into this
repository. It contains LISTEN-derived HRTFs and sample audio clips whose asset
licenses need a separate audit before redistribution.
