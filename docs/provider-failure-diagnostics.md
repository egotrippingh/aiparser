# Provider failure diagnostics

Base: production `d711aead8d1759309e660e09987bc039f5649e2c` (2026-10-22).

## Scope

Persist safe XMLRiver collection failure categories in the existing bounded provider
task history: timeout, transport, HTTP, API, malformed/incomplete response and
cancellation. Keep provider admission, retry timing, saved answers, ownership and
wallet settlement unchanged. Do not send additional live provider requests.

## Acceptance

- Distinguish failure stages and safe status/error codes without storing credentials,
  request URLs, prompt text, response bodies or arbitrary exception text.
- Retain the failed attempt's diagnostic across normal re-admission, bounded to the
  existing history limit; stale attempts cannot overwrite the current attempt.
- Cancellation remains cancellation; existing provider recovery and money gates pass.
- Release through a PR into production, exact-SHA CI, verified backup/isolated restore
  and live readiness. Observe a subsequent ordinary attempt without accelerating it.

## Evidence

Implementation is prepared. Shared XMLRiver/legacy checks: 71 passed; after the
ASCII-code normalization fix, the final XMLRiver text suite passed 34 tests.
Independent correctness and focused risk reviews found no blocking issues; an
independent narrow run passed 13 tests. Final additions cover stale/completed task
history and native cancellation. Full server tests and exact-SHA delivery/live
ordinary-attempt evidence are pending.

Local test logs: `C:/codex-tmp/provider-failure-diagnostics-20261022/`.

The persisted diagnostic records category, fixed reason/provider numeric code,
optional HTTP status, stage, timestamp, durable cycle and HTTP-attempt count. It
shares the existing last-32-entry history; older transition entries remain readable.
No diagnostic field is exposed through a new public API or written to the Git tree.
