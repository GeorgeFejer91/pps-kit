# Reactivity rules

Check the installed MobX version and configuration before applying examples.
The [observable-state documentation](https://mobx.js.org/observable-state.html)
defines the annotations and their limits.

- Use `makeAutoObservable` for a suitable non-inherited object or class. Use
  `makeObservable` for inheritance and explicit ownership. Existing correctly
  annotated stores do not need conversion to a different style.
- Exclude services and resource handles with explicit overrides. Use
  `observable.ref` for immutable snapshot replacement when that matches the
  contract; avoid recursively observing a native object graph.
- Keep computed getters pure. Use observable maps for changing keyed entities
  when that fits their identity and access pattern.

MobX records synchronous property reads inside a tracked function. Read the
relevant fields inside the observer, computed, or reaction data function.
Destructuring a primitive outside tracking creates a snapshot. Reads after an
`await` do not extend the earlier tracking scope. Use the primary
[reactivity guide](https://mobx.js.org/understanding-reactivity.html) to diagnose
the actual dependency graph before changing architecture.

The [actions guide](https://mobx.js.org/actions.html) defines transaction
boundaries. A continuation after `await` needs its own action boundary for
observable mutations, for example `runInAction`, or a suitable `flow`.
Include error/loading transitions in coherent transactions. Do not assume a
strict-action violation always throws; diagnostics depend on version/build.
Cancellation of a flow does not automatically abort its underlying network
request. Use the transport's abort mechanism and reject stale completions.

Give long-lived `autorun` and `reaction` subscriptions an explicit disposer.
Effect-based `when` disposes after its predicate succeeds; dispose it if its
owner ends first. Promise-based `when` has its own cancellation behavior.
Check [reaction lifetimes](https://mobx.js.org/reactions.html) for the chosen API.
Avoid reactions that only copy a derived value into another observable.

Export selected plain data at a boundary. `toJS` is useful when a consumer
requires a plain representation; it is not required for every library or render
and does not replace an explicit serialization/schema contract.
