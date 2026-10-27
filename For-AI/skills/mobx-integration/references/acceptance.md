# Acceptance evidence

Choose checks for the touched slice using the existing runner and the currently
authorized scope. Record missing tooling or permission honestly. Avoid creating
a second test framework or a broad migration to demonstrate one store.

| Boundary | Observable result |
| --- | --- |
| Source mutation and computed value | A subscribed consumer receives the intended derived result |
| Subscription granularity | An unrelated mutation does not trigger the tracked consumer unnecessarily |
| Async success, rejection, and races | Loading/error state remains coherent; stale results cannot replace newer accepted state |
| Cleanup and remount | A disposed owner receives no further effect; reopening does not accumulate listeners |
| UI adapter | The actual view updates through the selected binding or DOM reaction |
| IPC or remote state | Confirmed UI state follows authoritative receipts/revisions, including reconnect behavior |
| Performance-sensitive path | Before/after measurements use the same target, workload, and metric |

Use store-level checks for derivations and lifecycle, plus the real adapter
surface for rendering claims. A passing store check alone does not qualify a
Tauri command, React view, or game frame budget. Report workload, device/runtime,
sample conditions, and remaining acceptance gaps. Reuse the project's existing
evidence record and goal checklist.
