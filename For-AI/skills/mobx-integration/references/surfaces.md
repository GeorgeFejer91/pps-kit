# Application surfaces

## React

Read the [official React integration guide](https://mobx.js.org/react-integration.html).
Use the binding compatible with the project's React components and MobX version.
Functional consumers use `observer` from `mobx-react-lite` when appropriate.
Read observable fields in the observed render. Keep the store reference stable
through the existing provider or composition root. Preserve simple local React
state where it already fits. Use effects with cleanup for external subscriptions;
do not create unmanaged reactions during render. Preserve SSR request isolation
and apply the binding's server-rendering configuration when SSR is present.

## Plain HTML, other frameworks, and Tauri WebViews

Keep the chosen framework. Plain DOM consumers can render from a bounded
reaction with explicit teardown. A framework with its own reactive graph does
not need a second graph unless the shared-store boundary justifies it.

For Tauri, Rust retains application authority, validation, persistence, access
control, and durable operation identity. MobX owns UI intent and a view
projection. Apply validated snapshots/events using the existing revision rules.
Separate pending intent from confirmed authoritative state. An optimistic UI
change is not proof that a native command succeeded. Dispose IPC/event listeners
when their owner closes. Use the matching Tauri skill for native contracts.

## Games and high-frequency data

Menus, inventories, settings, editor panels, and progress are possible reactive
UI surfaces. Keep frame-critical simulation in its existing engine owner.
Bridge selected changes or bounded snapshots at the UI's required cadence.
Measure notification count, frame time, input latency, and allocation on the
actual target before expanding observable coverage. Avoid copying the whole
world into an observable tree each frame. Do not assume MobX is either a frame
engine or categorically unsuitable for every high-frequency use case.

## Scope of the MVVM example

The [React MobX MVVM repository](https://github.com/utilitydelta/react-mobx-mvvm)
illustrates injectable services and view-model boundaries. Its custom async
transform and architectural preferences are project choices. Standard MobX
actions and the existing application composition remain the default here.
