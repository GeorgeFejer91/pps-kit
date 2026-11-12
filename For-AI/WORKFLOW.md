# Development stages

Record the requested stage in [CURRENT_WORK.md](CURRENT_WORK.md). A task can
finish at any explicitly requested stage; report later gates as deferred.
Documentation/tooling-only work goes straight to its relevant source checks.

| Stage | Work and evidence | Exit condition |
|---|---|---|
| Local preview | One scoped screen/behavior, canonical frontend build, and local real-control and inspected visual checks. | Working preview. Continue to deployment for completed Pages UI changes unless the user requested a preview-only or local-only task. |
| Verified source | Requested behavior verified, owning tests passed, scientific contracts preserved or intentionally documented, and compiled local/Pages parity confirmed for UI. | Scoped source checkpoint pushed. For Pages UI, the deployment and changed behavior are verified on ppskit.com before handoff. |
| Packaged candidate | Build exact verified revision; component inventory, runtime dependencies, installed executable/UI checks. | Evidence from the installed path, with scientific qualification gaps stated. |
| Qualified release | Clean-install/download checks, platform/hardware/scientific gates matching release claims, final URLs/hashes/metadata. | Authorized release publication with retained evidence. |

## Delegation and handoffs

Default to one agent. When delegation is authorized and there is useful
independent work, the coordinator assigns bounded work packages to up to
three workers, within the harness limit. Organize packages under their owning
domain; keep the running hierarchy to coordinator → workers or reviewers.
A worker that needs help returns the proposed subtask to the coordinator to
assign as a sibling. No nested orchestrator or separate progress ledger.

- **Assignment:** give each worker the outcome, one domain and its
  [skill route](SKILLS.md#skill-nesting-and-ownership), exclusive write paths
  (or read-only scope), dependencies, and a named acceptance check. Use a
  managed worktree for independent edits when it helps. Workers preserve
  changes outside their scope and report overlaps to the coordinator.
- **Order:** split only when separate owners can deliver verifiable results.
  Keep shared schema, actor and compiled artifact changes with a single owner
  and integrate them serially. Use a read-only reviewer when independent
  review is required and the harness has capacity.
- **Return:** workers report changed paths or commit, check results, and open
  blockers. The coordinator checks diffs and evidence, runs the shared gate,
  updates [CURRENT_WORK.md](CURRENT_WORK.md), and owns the Git checkpoint.
  Delegation does not extend release or publication authorization.

## UI exploration and promotion

Use existing source/build paths. Run previews locally with real controls and
representative states, widths, long labels, accessibility, and error cases.
Designer uses `npm --prefix apps/designer/frontend run build`; Runner frontend
uses `npm --prefix apps/runner run check`. Serve/test the compiled artifact
through the actual relevant local application path.

Use silent, isolated background browser checks unless the user asks otherwise.
Designer visual audit:

```powershell
python For-AI/engineering/validation/scripts/run_designer_visual_layout_audit.py
```

Inspect the rendered evidence and correct defects. Backend and unit tests
supplement real interaction checks.

The owner grants standing authorization to deploy every completed UI task that
changes the GitHub Pages site. After local verification, promote the scoped change
to `main` without a separate approval step. An explicit preview-only, review-only,
or local-only request sets the endpoint for that task.

Rebuild the canonical compiled assets and assemble and check Pages:

```powershell
node --test For-AI/engineering/automation/build_pages.test.mjs
node For-AI/engineering/automation/build_pages.mjs
```

Pages consumes the canonical Designer and allowlisted Runner bytes. Use the
same source and compiled assets for local and hosted checks. Keep editable UI
source in the frontend and Pages wrappers in `website/`.

Commit the scoped source and canonical artifacts, then push to `main` to start
[Publish GitHub Pages](../.github/workflows/pages.yml). Follow the run for the
pushed revision through deployment, address recoverable failures, and verify the
changed UI and affected routes on [ppskit.com](https://ppskit.com/). Compare the
live site with the assembled files using
[the public Pages byte audit](engineering/validation/scripts/run_public_pages_byte_audit.py).
Record the deployed commit, run, and live evidence in [CURRENT_WORK.md](CURRENT_WORK.md)
before handoff. [Git checkpoints](agent_update_protocol.md) cover safe pushes
and blocked publication.

## Packaging is a separate gate

Local preview/source tasks do not automatically rebuild installers. Before a
packaging task, select the verified revision and read the
[component inventory](download_package_inventory.md) and matching release
protocol. Rebuild affected executables, check runtime/plugin/ASIO requirements,
and exercise installed controls, not just source launchers. Report precisely
which source revision an existing installer contains.

An installed candidate is not qualified acquisition. Software/emulated tests,
device route timing, tactile perception, collected responses, and published
effect replication remain separate evidence layers. Preserve the V1
compatibility path while candidate V2 work proceeds; attach qualification only
to a named profile/route with retrievable evidence. Defer signing, release assets, and
public download promotion until the release task's actual authorization and
qualification requirements are satisfied.
