# Experiment Runner Pages Companion — 2026-08-30

## Outcome

The canonical Runner browser companion is staged for publication at the real
GitHub Pages subpage `/experiment-runner/`. The custom-domain and project-Pages
URLs to verify after the first deployment are:

- `https://ppskit.qzz.io/experiment-runner/`
- `https://georgefejer91.github.io/pps-kit/experiment-runner/`

Pages receives the same compiled HTML and browser assets as the local Runner
package. The desktop Tauri entry, bridge, native capabilities, private data, and
generated experiment outputs are excluded.

## Published allowlist

| Canonical input | Bytes | SHA-256 |
| --- | ---: | --- |
| `compiled/companion/index.html` | 9,999 | `B8109871A85A25FF5760882F8A134D76080D255C61903395E2B937D1D98C47FB` |
| `compiled/assets/companion.js` | 69,474 | `09020A7E8C138C4394FC7FDCD813999A43DAE96F602CBEF7DD7C0401B3E038F1` |
| `compiled/assets/qr-code.js` | 43,115 | `60D144F44E1CBCD9DC0990419CE07AAD85E07221F82EB4B496FA9D7C665470BD` |
| `compiled/assets/style.css` | 11,811 | `FFE81FF9A09CF6CB8B43E3EB7EE30B8B9F820B8ADB2179539AAD314F2F6590F5` |

The assembly test compares every staged file byte-for-byte and rejects
`assets/desktop.js`, any script/link resource outside the three-resource
companion allowlist, a changed CNAME, and private output roots.

## Automated checks

- Runner Node tests: 21 passed.
- Runner Vite production build: passed with no runtime CDN.
- Pages assembly test: 1 passed.
- Focused Designer static-packaging pytest: 1 passed.
- Pages staging and canonical/staged SHA-256 comparisons: passed.
- Companion metadata includes a restrictive same-origin CSP and
  `Referrer-Policy: no-referrer` equivalent meta policy.
- Invitation cleanup rejects query-string secrets and now scrubs both fragment
  and forbidden query material from browser history.

## Interactive browser verification

The actual staged Pages artifact was served locally and exercised through
attended browser mouse interactions. The saved completion-state capture is
[experiment_runner_pages_companion_20260830.png](./experiment_runner_pages_companion_20260830.png).
It is a 1,425 x 891 PNG (46,420 bytes; SHA-256
`CE4A7C2BCBFA3EC5F29E4685ABA569EB7B31C9AF610F4A3E65C7241948186AD8`).

- At `1440 x 900`, Controller mode rendered as a centered bounded companion
  surface with inert Connect and semantic action controls before invitation.
- At `390 x 844`, the layout had no horizontal overflow and switched to Phone
  Experiment mode through the visible mode control.
- Visual inspection exposed and fixed a hidden-pairing CSS override; the QR and
  relay controls now remain absent until **Create target and invitation** is
  clicked.
- The smartphone flow completed through visible controls: create target,
  prepare demo, submit setup, locally arm audio/vibration, start, pause, resume,
  and stop. The target reached `Completed`, revision 7, with `Stopped cleanly`
  and an enabled event-log download control.
- The hosted site's Downloads > Companion section displayed the new card and a
  new-tab link to the canonical subpage with `rel="noopener noreferrer"`.
- Browser console inspection found no error or warning during the phone-local
  flow.

The Runner frontend dependency audit is clean. The existing Designer build
still pins Vite 6.1.0 and `npm ci` reports three development/build-chain
advisories (two high, one moderate); Vite is not included in the production
static runtime. Updating that separate Designer toolchain remains follow-up
work rather than being silently mixed into this route change.

## Qualification boundary

This validates static publication assembly, responsive browser interaction, and
the exploratory phone-local demo. Public URL readback remains pending the first
post-push Pages workflow. It does not validate an external relay, physical
smartphone audio/vibration timing, background behavior, or publication-grade
stimulus onset. GitHub Pages cannot host WebSocket upgrades; cross-device BRSP
control remains blocked until a browser-side WSS/WebRTC adapter and endpoint are
implemented/configured, deployed, and qualified together. Tauri invitations
therefore remain local rather than being repointed to this public route.
