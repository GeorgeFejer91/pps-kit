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

Current evidence: script parsing, locked toolchain/runtime preflight and CLI
argument checks pass. Full bundling, payload inspection, clean installation,
native dialogs, offline profile import, generation and complete result audit
remain release checks. Keep those states distinct in `CURRENT_WORK.md`.
