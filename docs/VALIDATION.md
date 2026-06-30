# Validation Tiers

Use `tools/check_all.ps1` as the repo-local validation entrypoint.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_all.ps1 -Tier Quick
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_all.ps1 -Tier Standard
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_all.ps1 -Tier Deep
```

## Quick

Fresh-clone-safe checks for routine code changes:

- compile Python sources under `src`, `tests`, `tools`, `validation_protocols`, and `windows`
- parse tracked JSON files used by assets, configs, templates, project memory, and packaging
- run the release/privacy audit
- run a focused pytest subset covering release inventory, package metadata, seed data, CLI smoke tests, Focus runner launch contracts, and the paper-audit package seam
- run `git diff --check`

Android runner companion changes should also run:

```powershell
android\runner-companion\gradlew.bat testDebugUnitTest assembleDebug
```

This is separate from `tools\check_all.ps1` because it requires JDK 17,
Android SDK 37, and first-run Gradle dependency resolution.

## Standard

Standard runs Quick plus the full tracked-file pytest suite. It may take longer than five minutes on this Windows workstation and should be used before structural merges or releases.

## Deep

Deep runs Standard and exposes opt-in generated-artifact and hardware gates:

- `-AllowGeneratedArtifacts` may refresh ignored/local paper-audit extraction inventories and tracked audit summaries.
- `-AllowHardware` is reserved for configured lab PCs with the required ASIO, LSL, XDF, and loopback setup.

Do not treat skipped Deep hardware work as participant-readiness evidence. Hardware and packaged-runner claims still require the relevant validation scripts under `validation_protocols/` and their generated evidence folders.

## Paper-Audit Boundary

The paper-audit pipeline is core validation input for published-study support. Tracked audit outputs may include schemas, compact ledgers, manual reviews, source pointers, hashes, and blocker summaries. Raw PDFs, supplements, extracted full text, page images, and local resume ZIPs stay under ignored `artifacts/paper_metadata_audit/`.
