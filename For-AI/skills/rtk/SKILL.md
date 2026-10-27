---
name: rtk
description: Reduce coding-agent shell-output tokens with rtk-ai/rtk. Use for repository inspection, search, build and test output; preserve exact output for editing, parsing and verification.
---

# RTK command output

Prefer the installed [rtk-ai/rtk](https://github.com/rtk-ai/rtk) CLI for supported, human-read shell output. Filter at the tool boundary, before output enters context. Keep searches scoped and load only task-relevant context; compressed noise is still noise.

## Check once per environment

Run `rtk --version` and `rtk gain` to confirm the token optimizer, rather than the unrelated crates.io package. This Windows installation uses `%LOCALAPPDATA%\Programs\RTK\bin\rtk.exe`; an already running shell may need that absolute path until restarted. The source checkout is `Documents\GitHub\rtk`.

If missing, continue with bounded native commands and report the fallback. During authorized setup, use the upstream installation guide: `winget install --id rtk-ai.rtk --exact`, or a checksum-verified official release. For Cargo, use `cargo install --git https://github.com/rtk-ai/rtk rtk`, not bare `cargo install rtk`. RTK is an agent tool, not an application dependency; do not add it to product manifests, builds or shipped assets.

## Normal use

```text
rtk git status
rtk git diff --stat
rtk git log -5
rtk rg -n "pattern" src
rtk read -m 80 path/to/source.rs
rtk cargo test
rtk test <test-runner> <arguments>
rtk gain --format json
```

Run from the repository root, or use `rtk git -C <root> status`. Check `rtk <subcommand> --help` for the installed version before using unfamiliar flags. Prefix supported external commands explicitly in PowerShell and Codex execution tools; do not prefix PowerShell cmdlets or assume a Bash hook intercepts every execution tool.

Compression is lossy. Structural `rtk read -m` previews help navigation; read complete instructions and exact affected code before editing. Use native reads, raw `git diff`, and native `rg` when exact lines, exhaustive matches or machine-readable output matter. Keep JSON, CSV, hashes, Git porcelain and other parser inputs unfiltered. `rtk bypass <command> <arguments>` runs an external command without filtering; `rtk recall` can recover retained output when RTK reports a recovery reference.

Preserve command arguments, working directory and exit status. A compact summary does not prove tests passed: check the exit code and inspect complete relevant failures. Never rerun a mutation merely to recover its output. Existing authorization and Git publication rules still apply to wrapped commands.

## Integration and evidence

The portable integration is this skill plus its short project route. Optional native Codex hooks can be previewed with `rtk init -g --codex --dry-run`; install only when the current host supports them, preserve existing hooks and instructions, and verify a real rewrite. Direct prefixes work without hooks. Do not configure the optional API proxy, services, provider routing or telemetry merely to enable shell filtering.

Use `rtk gain --format json` before and after comparable commands to measure saved shell-output tokens. Counts are approximate; do not equate their reduction with total conversation cost or total context reduction. Consult the [upstream guide](https://github.com/rtk-ai/rtk/tree/master/docs/guide) for version-specific details. This guide was checked against RTK 1.0.1.
