# Durable answer capture and adaptive scan timing

Requested 2026-10-06: overlap browser capture with analysis and add adaptive
inter-query pacing. Multi-account execution and infrastructure changes are out
of scope. Base: production fdacff6; prepared agent version: 2026.10.6.1.

## Acceptance

- Persist answer text, sources, extra analysis fields, screenshot and immutable
  analysis/check/owner inputs before the browser submits another query.
- Bound accepted backlog and analysis concurrency. Browser producers continue
  while analysis runs; queue backpressure counts toward the inter-query pause.
- Final progress and billing represent completed analysis. Pause/stop prevent
  further browser admission; accepted captures drain before terminal completion.
- Interrupted captured work resumes analysis without asking the provider again.
  Ordinary analysis failures require explicit continuation; payload is retained.
- Atomically persist result, outboxes and capture state. Preserve canonical
  managed query UUIDs and payer ownership; retries cannot double charge.
- Pending captures protect their projects/queries against destructive deletion.
- New scan snapshots freeze adaptive policy bounds. Legacy continuations retain
  fixed timings. Explicit provider throttling increases pacing, clean successes
  recover gradually, and delays never fall below measured provider floors.
- Capture readiness, source extraction, formatting and provider generation waits
  remain unchanged. Generic network/LLM failures are not throttling evidence.

## Implementation boundaries

Use the existing SQLite and asyncio machinery: one additive durable capture
table, a small bounded analysis queue, and monotonic next-query deadlines.
One scan-wide worker analyzes answers, two can wait in its queue, and each
active provider can hold one persisted answer while waiting for admission.
Completed payloads are removed only in the result/outbox transaction. Failed
payloads retain their reservation and block project/query deletion until retried.
Current SQLite connections are autocommit: multi-write finalization requires an
explicit transaction. Screenshot exports must use scan-specific paths.

Managed cancellation currently rejects analysis immediately. Allow analysis
and arbitration of already-reserved checks only while the assigned run remains
active with an unexpired lease. New reservations and wrong/revoked devices,
foreign owners and terminal runs remain forbidden. Existing upfront reservation
does not prove capture; this narrow permission must receive focused risk review.
The server authorizes previously reserved checks, not proof of browser capture.
It therefore can analyze any already-reserved check of the same live assigned
run after a stop request. The client admits no new browser queries after stop;
cached primary/arbiter replay remains idempotent. No new server migration or
capture-acknowledgment protocol is introduced.

Check credentials before processing pending work. Account changes must not send
old captures through a new payer's credentials. Keep the controller active until
accepted analysis drains and retain work on task cancellation.

## Verification and delivery

Prove overlap with a deliberately blocked analyzer; test bounded backlog,
pause/stop, capture and finalization crashes, explicit analysis retry, schema
initialization, frozen legacy timing, recovered ChatGPT throttle and managed
cancellation/ownership/lease boundaries. Run affected existing suites, scan
benchmark self-check, independent correctness and risk review.

Deliver as a feature PR into production. Prepared code and deterministic checks
do not establish live provider throughput or a published Windows release.

## Verification evidence

Local deterministic checks: full server suite 72 passed; affected agent suites
54 passed; parallel execution 11 passed; planning 15 passed. Final capture,
billing/timing and desktop subset 36 passed; final capture suite 19 passed. Benchmark
`--self-check` passed. New server authorization cases cover live cancelled
reserved/settled replay, foreign owners/devices, revoked devices, terminal runs,
expired/missing leases and paused recovery. Existing deprecation warnings remain.

Graph refresh uses `graphify update .`, AST-only. Prepared agent version is
2026.10.6.1; published Windows 2026.10.2.3 and production fdacff6 remain unchanged.
Live scans, installed-EXE upgrade, sustained provider throttling, actual speed
and power-loss behavior on a real user profile remain unverified. All new checks
use temporary databases and fake providers; no paid user scan was launched.
Frontend: 50 tests passed; lint exited 0 with existing warnings; production build
passed and its tracked `web/` output was refreshed. Final independent correctness
and focused financial/auth/data-loss reviews found no remaining substantiated
defect. No new scan is admitted while the project still has retained answers
from another scan; this keeps their continuation and reservation reachable.

Delivery: [PR #26](https://github.com/egotrippingh/aiparser/pull/26) targets
`production`; implementation commit `8e254bc83a3b5a5010bbe7a433b07ba6be13a463`
passed [Tests and build](https://github.com/egotrippingh/aiparser/actions/runs/37530025581).
Production deployment was correctly skipped for the PR. This is prepared source,
not a published Windows release or verified live throughput.
