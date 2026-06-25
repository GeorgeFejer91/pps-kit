# Internal Validation Acceptance Report

Run ID:

Date:

Operator:

Git commit/status:

Session folder:

Validation output folder:

Living LaTeX report:

## Scope

- [ ] GUI-to-artifact traceability
- [ ] Dummy 3-channel WAV routing
- [ ] Audio-vs-tactile electrical skew
- [ ] Electrical loopback latency
- [ ] Session event logging
- [ ] LSL marker reliability
- [ ] Emulated mouse-click timing
- [ ] End-to-end stress matrix

## Results

| Area | Pass/Review/Fail | Evidence |
| --- | --- | --- |
| GUI traceability | Review | |
| Single 3-channel WAV routing | Review | |
| Channel isolation / no downmix | Review | |
| Audio-vs-tactile electrical skew | Review | |
| Electrical loopback | Review | |
| Session event logs | Review | |
| LSL markers | Review | |
| Mouse to response marker | Review | |
| Session loopback validation | Review | |

## Latency Budget

| Component | Estimate | Evidence |
| --- | ---: | --- |
| Electrical output-to-input median | | |
| Left/right electrical skew | | |
| Tactile-vs-audio electrical skew | | |
| Electrical p95 residual jitter | | |
| Callback/log timing behavior | | |
| LSL probe arrival behavior | | |
| Mouse to response marker median | | |
| Mouse to response marker p95 | | |
| Session physical residual p95 | | |

## Not Measured

- Woojer mechanical vibration onset unless an external sensor was used.
- Human reaction time.
- Bluetooth tactile timing.

## Open Issues

- 

## Acceptance Decision

- [ ] Accepted for internal timing confidence
- [ ] Accepted with documented limitations
- [ ] Review required before participant use
- [ ] Failed
