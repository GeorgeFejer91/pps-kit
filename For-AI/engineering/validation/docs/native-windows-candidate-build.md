# Native Windows candidate build

This route builds unsigned local NSIS candidates; it does not install, sign or
publish them. Keep the Designer identifier proposal pending until approved.
The existing Runner identifier is `org.peripersonalspace.runner.preview`.
An installed or clean-Windows result requires a separate recorded test.

Use [Build_PPS_Native_Candidate.ps1](../../build/windows/Build_PPS_Native_Candidate.ps1)
with a new output directory, the separately verified renderer directory, its
SHA256 and matching source commit, and a directory containing the six exact
files in [native-runtime-lock.json](../../build/windows/native-runtime-lock.json).
`-Apps runner` builds only Runner. `-ValidateOnly` checks the inputs and prints
the proposed manifest without creating output. `-NpmCliPath` accepts an existing
pinned npm CLI when npm is not on PATH. Node 24.19.0, npm 10.9.4, Rust 1.96.0
and the repository's Tauri CLI 2.11.4 lock are required.

The runtime inputs are x64 Microsoft redistribution files, not copies from
System32. The VC14 files come from the installed Build Tools redistribution
directory; their matching English license is the `license.rtf` payload in the
same redistribution executable. The VC2013 package URL/hash is recorded in the
lock. Its signed embedded cabinet contains `F_CENTRAL_msvcr120_x64`, copied as
`msvcr120.dll`; its bootstrap cabinet's `license.rtf` payload becomes
`VC2013-license.rtf`. Extracting these inputs does not run an installer. The
reviewed DLLs have valid Microsoft Authenticode signatures. The builder checks
every DLL/license hash before copying any into the candidate.
The builder stages writable copies without modifying those inputs. CAB-extracted
read-only notices otherwise make a subsequent Tauri resource copy fail. Identical
read-only outputs from the old builder are normalized only after hash and
ancestor-link checks; differing or linked outputs fail explicitly.

The retained SOFA dependency DLLs require the legacy VC2013 runtime; Microsoft
no longer supports that runtime. This build preserves the tested renderer ABI
and records the dependency explicitly. Source modernization needs separate
waveform and loader verification. The native host currently accepts the fixed,
bundled HRTF resource, not arbitrary remote HRTF input.

The builder checks committed product source, the renderer source revision,
fresh output ownership, locked dependencies and canonical frontend drift.
It supplies app-local runtime DLLs beside both native applications and the
renderer child, the existing media/HRTF/template resources, third-party notices
and offline WebView2 setup. The corresponding renderer source archive is a
separate artifact. `For-AI/`, Python, source checkouts and development runtimes
are not installer resources. `candidate-manifest.json` and `SHA256SUMS` identify
the exact source, build inputs and resulting files.

Runner candidate at source `b8e0e7895c956652eb2e7e282ff49633d186109b` built
successfully: the unsigned NSIS installer is 220,510,500 bytes with SHA256
`25796b62ceee24a4a0c75de7e3dd1b5f701726b25f9458adef412a1dcdd33cb2`.
Its 24-file payload contains the canonical web files, app-local VC14 DLLs and
offline WebView2 installer, with no Python, checkout or `For-AI/` payload.
The embedded WebView2 installer has a valid Microsoft signature and SHA256
`1c401b327fbc7bb9731b4e350a2194f083cbc3ede46508d52e1cae6610a39bea`.

A fresh current-user installation outside the checkouts passed actual native
WebView/IPC startup. The installed executable matched the extracted payload;
the process used its install directory and a Windows-only PATH. Its frontend
loaded from `http://tauri.localhost/` and matched the canonical desktop JS hash.
No package was selected, output reserved, target armed or experiment executed.
The owned test process was stopped afterward. This host already had WebView2;
the check does not establish clean-Windows prerequisite installation.

Evidence is retained under ignored `artifacts/native-candidate-runner-20261027/`,
`artifacts/native-runner-payload-report.json` and
`artifacts/ui-workflow-check/runner-actual-native-startup-report.json`.
An updated Runner candidate at `468c8241d7979f1e02aec35f9f3102f46988e6aa`
also built and installed successfully after correcting the repeat-build notice
failure. Its installer is 220,510,559 bytes, SHA256
`5db890862e29b9bf7b6cede9a3abfc29420b2635b807941eef390b7ca5e0a23a`.
All ten canonical web files and pinned runtime files match the 24-file payload;
the installed executable matches the extracted executable. A fresh launch/IPC
check was rejected by automatic approval review with only "blocked by policy";
startup at this updated revision remains unverified. See ignored
`artifacts/native-candidate-runner-20261027-r3/` and
`artifacts/native-runner-r3-payload-report.json`. The earlier startup evidence
above belongs only to `b8e0e789`, not to this replacement package.

The final integrated source at `9dfd176063997fddfe36ac8a8c5a2a38e2b6b428`
was rebuilt and installed on 2026-10-28 using the pinned builder/toolchain.
Its unsigned Runner-only NSIS installer is 220,505,585 bytes, SHA256
`3fdbe2bd33c3fef3b444b44441e362e34ea5b3a67c98e2319d145788bfa2873f`.
The audited 24-file payload contains ten canonical web files with identical
hashes, the pinned application-local VC14 files and the signed offline WebView2
installer; no Python, source checkout or `For-AI/` is present. Installation
returned zero and all 16 installed application/runtime/web files match the
extracted payload. The existing preview application was not running before
installation. This check did not launch the application or exercise any control.
The earlier automatic-review launch rejection remains in force; no alternate
launch was attempted. This host already had WebView2, so prerequisite setup on
clean Windows remains untested.

Evidence is retained in ignored `artifacts/native-candidate-runner-20261028-r1/`,
`artifacts/native-runner-9dfd-payload-report.json` and
`artifacts/native-runner-9dfd-installed-payload-report.json`. The candidate
manifest and `SHA256SUMS` bind the verified renderer/runtime inputs and separate
renderer source archive. No public download was changed.

Later product source/UI changes need their own rebuilt candidate. Designer packaging,
native file dialogs, clean-Windows operation and the complete installed
import/generate/execute/result journey remain release checks. Keep those states
distinct in `CURRENT_WORK.md`.
