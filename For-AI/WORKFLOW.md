# Development stages

Record the requested stage in [CURRENT_WORK.md](CURRENT_WORK.md). A task can
finish at any explicitly requested stage; report later gates as deferred.
Documentation/tooling-only work goes straight to its relevant source checks.

| Stage | Work and evidence | Exit condition |
|---|---|---|
| Local preview | One scoped screen/behavior; canonical frontend build; local real-control and inspected visual checks. | Concrete working preview. Unsettled design remains here for user review. |
| Verified source | Accepted behavior; owning tests; unchanged scientific contracts or intentional documented changes; compiled local/Pages parity for UI. | Scoped source checkpoint committed/pushed; hosted route checked after promotion to `main`. |
| Packaged candidate | Build exact verified revision; component inventory, runtime dependencies, installed executable/UI checks. | Evidence from the installed path, with scientific qualification gaps stated. |
| Qualified release | Clean-install/download checks, platform/hardware/scientific gates matching release claims, final URLs/hashes/metadata. | Authorized release publication with retained evidence. |

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

Inspect its rendered evidence; correct defects before a usability claim.
Backend/unit tests supplement that proof. If the user requested exploration or
the appearance remains unsettled, present the working local preview for review.
If the requested outcome is already authorized and verified, do not ask for
another routine confirmation.

Keep unsettled but verified checkpoints on a review branch. The Pages workflow
deploys matching product changes pushed to `main`; a push there is publication,
not merely local backup. At promotion, rebuild canonical compiled assets and
assemble/check Pages with:

```powershell
node --test For-AI/engineering/automation/build_pages.test.mjs
node For-AI/engineering/automation/build_pages.mjs
```

Pages consumes the same Designer and allowlisted Runner companion bytes.
Never create a second editable dashboard under `website/`. Verify live routes
after a production UI push. Git checkpoint rules are in
[agent_update_protocol.md](agent_update_protocol.md).

## Packaging is a separate gate

Local preview/source tasks do not automatically rebuild installers. Before a
packaging task, select the verified revision and read the
[component inventory](download_package_inventory.md) and matching release
protocol. Rebuild affected executables, check runtime/plugin/ASIO requirements,
and exercise installed controls, not just source launchers. Report precisely
which source revision an existing installer contains.

An installed candidate is not qualified acquisition. Software/emulated tests,
device route timing, tactile perception, collected responses, and published
effect replication remain separate evidence layers. Preserve the qualified V1
path while candidate V2 work proceeds. Defer signing, release assets, and
public download promotion until the release task's actual authorization and
qualification requirements are satisfied.
