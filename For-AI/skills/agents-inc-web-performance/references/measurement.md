# Measurement scope

For public web experiences, consult the [Core Web Vitals definitions](https://web.dev/articles/vitals).
Good field thresholds are LCP at most 2.5 seconds, INP at most 200 milliseconds,
and CLS at most 0.1, assessed at the 75th percentile for the relevant population.
Identify whether evidence is a lab observation or field data. A local WebView
or offline desktop task can require different startup and interaction metrics.

For desktop or game interfaces, record startup-to-usable time, input-to-visible
response, update/frame cost, allocation, and retained listeners as relevant.
Measure IPC or remote round trips separately from local store updates. A faster
JavaScript derivation does not prove a faster remote control path.

Bundle budgets identify the artifact, compression, loading stage, and target.
There is no universal 200 KB limit. Choose code splitting where avoided work
exceeds its fetching and coordination cost. Do not lazy-load a critical surface
without measuring the resulting interaction and layout behavior.

Virtualization needs evidence from the actual row complexity, device, navigation,
and accessibility contract. There is no universal hundred-row cutoff. Keep the
existing no-scroll, full-text, paging, focus, and selection requirements intact.

[React streaming SSR](https://react.dev/reference/react-dom/server/renderToPipeableStream)
supports Suspense boundaries; lazy content is not categorically absent from the
server response. Tree shaking depends on module format, side effects, bundler
analysis, and actual usage, so inspect the emitted result.
