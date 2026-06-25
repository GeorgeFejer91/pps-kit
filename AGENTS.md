# Agent Start Here

Before working in this repository, read [For-AI/README.md](For-AI/README.md).

This repo uses `For-AI/` as tracked project memory for future AI agents. Keep it current when project goals, GUI behavior, data schemas, runner behavior, publication constraints, tests, or repo structure change.

Every completed repository change must be committed and pushed to GitHub before finalizing. Stage only the intended change set and do not bundle unrelated dirty worktree changes. If pushing is blocked, report the exact blocker and leave the work ready to push.

When changing the HTML dashboard, always keep the packaged local dashboard and the online/static GitHub Pages dashboard in sync in the same change set. Do not finalize a local HTML GUI update unless the online-facing HTML/CSS/JS assets are updated and verified too.
If either the packaged local dashboard or the online/static GitHub Pages dashboard changes, update the other side in the same change set and push immediately so the website reflects the same GUI state.
## Quest ADB Access

For headset work, use the workspace-stable ADB wrapper so every project shares the same RSA key and the Quest does not fall back to `unauthorized`:

- Run `adb devices -l` from a new terminal; it should resolve to `D:\GithubVR\tools\adb.cmd`.
- If PATH is stale, run `D:\GithubVR\tools\adb.cmd devices -l`.
- Expected authorized headset: `2G0YC1ZG1002QL device product:eureka model:Quest_3`.
- Do not rotate or delete the `adbkey` or `adbkey.pub` files in the `ADB_VENDOR_KEYS`-pinned `.android` key folder.
- If the headset reports `unauthorized`, approve **Always allow from this computer** inside the headset and see `D:\GithubVR\QUEST_HEADSET_ACCESS.md`.
