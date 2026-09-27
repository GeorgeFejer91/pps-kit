# Agent maintenance and Git checkpoints

## Start and scope

Read `AGENTS.md`, [README.md](README.md), [CURRENT_WORK.md](CURRENT_WORK.md),
and the matching domain. Load references by task, not the whole memory archive.
State the requested outcome and stage before substantive work. Existing user
authorization takes precedence; do not add redundant approval questions.

Inspect Git status and fetch the remote before editing. With a clean worktree,
use fast-forward-only pull on the selected branch. Preserve unrelated edits
before any synchronization that could affect them. If history diverged or was
rewritten, do not reset, force-push, or merge it blindly; retain the prior
branch/work in a recoverable checkout and establish the intended baseline.

## Stage and verify

Follow [WORKFLOW.md](WORKFLOW.md). Local UI previews precede source promotion;
packaging/release are explicit later stages. User-facing behavior requires
real control interaction; visual changes also require inspected rendered
screenshots/geometry. APIs, unit tests, mocks, and compiled artifacts alone do
not establish usability, installed behavior, physical timing, or replication.

At UI promotion, rebuild the canonical compiled frontend and assemble Pages
from its identical allowlisted bytes. Keep relative assets and local/native
orchestration boundaries. `website/` is a wrapper/input tree, not another UI.
Live hosted verification follows a production UI push. Preserve public routes,
CNAME, and origin-only CORS settings described in the release domain and
architecture. Never publish desktop Tauri privileges or participant data.

## Automatic agent checkpoints

After each completed, verified logical change or independent subtask, and
before handing back the task:

1. Update the owning guidance/decision only if a durable contract changed;
   update current work at an actual stage transition.
2. Inspect the diff and run the smallest relevant checks plus whitespace checks.
3. Stage exact intended paths, inspect the staged diff, and commit a concise
   problem/outcome message. Never bundle unrelated edits or use blanket staging.
4. Push the task branch and verify the remote branch points to the local commit.
   Use a review branch for verified but unsettled UI previews; promote to `main`
   only after the stage's acceptance and parity gates pass.

These are agent execution rules, not a filesystem watcher, timer, commit hook,
or background auto-push daemon. Do not commit each keystroke, knowingly broken
work, secrets, or generated/private artifacts. A user request to hold commits,
pushes, or work locally overrides the default. If Git blocks publication,
report the exact error and retained local commit/staged state; do not force it.

## Keep memory small

Replace superseded current guidance rather than appending session transcripts.
Update only the owning domain, scientific contract, or current decision.
[evolving_goals.md](evolving_goals.md) holds durable direction;
[module_map.md](module_map.md) holds ownership; detailed evidence stays in its
existing research/validation location. Archive superseded long-form memory
with a source checkpoint instead of deleting useful scientific decisions.
Never store credentials, raw papers/recordings, participant data, generated
runs, machine-specific absolute paths, or unsupported scientific claims.

Final reports state the stage delivered, relevant verification/gaps, whether
memory was updated, and the commit/push result. A local preview or source-only
task may finish with packaging explicitly deferred.
