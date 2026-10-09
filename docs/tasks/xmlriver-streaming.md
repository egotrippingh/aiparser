# Непрерывный сбор и анализ ответов

Base: production `8031019`, branch `codex/xmlriver-streaming`, initial merge `8b1781f`.
Pre-existing changes: none; preserved prior delivery docs commit `7691f04`.

Outcome: Google and Yandex collect simultaneously at 10 slots each, independently
replenished. Every durable response immediately enters analysis; no batch barrier.
Primary and arbiter share 20 model slots. This is our capacity, not a provider guarantee.
Collection supplier is confidential: no supplier names in interface copy or errors,
including historical errors. Preserve original evidence and database history.

Scope: cloud worker/tick/capture/result settlement, AI retry hints, PostgreSQL pool;
frontend answer component, service/settings copy, public error presentation.
Keep: ownership, frozen inputs/prices, 4 model attempts, 6 collection attempts,
90-second collection timeout, durable answers, idempotent charges, agent compatibility.
No schema migration or installer publication planned.

Acceptance:
- Fast response analyzed/published while another collection remains blocked.
- Collection continues while models run; models overlap within shared limit.
- Separate Google/Yandex limits replenished continuously; no unbounded task creation.
- Stop/pause/shutdown block new admissions and drain already-admitted responses/models.
  Model admission is the fresh owner/state read after obtaining the Check lock.
- Lease heartbeat survives slow calls; stale owner cannot publish/charge after takeover.
- Same check settles once; cached analysis survives recovery; errors preserve siblings.
- Historical supplier errors hidden without altering saved answer/evidence.
- Existing server suite and focused regression checks pass; disposable PostgreSQL 16
  concurrency check proves independent transactions, stop and fencing behavior.
- Frontend test/lint/build plus desktop/narrow disposable browser smoke.
- Independent correctness and risk review, exact-SHA CI/deployment/public smoke.

Steps: interface confidentiality first (root sole writer); server pipeline second
(builder sole writer); independent review; authorized production release.
Evidence: historical supplier error regression failed on initial tree before fix.
Implemented source: `3e84bd5` (pipeline `d9b57ee`, confidentiality `ac1ac31`).
Final review fixes: cached verdict remains usable after Stop; one throttled engine
does not pause the healthy engine until its queue drains. Both regressions failed
before the fixes and passed after. Unexpected task/save failures still pause at once.

Checks: initial full disposable PostgreSQL-enabled server suite 140 passed; final
two regressions added, final suite pending. PostgreSQL 16 uses isolated schemas,
fake providers and a loopback-only disposable instance. Frontend 58 tests passed,
lint has existing warnings/no errors, build passed. Desktop and 390px fake browser
checks passed: carousel/highlights, image/API failures, no overflow or console errors.
Sol correctness and Astra risk reviews are rechecking the final two fixes.

Limits: one cloud run is drained at a time; different projects remain sequential.
Multiple worker processes require a shared account limiter. Account-limit discovery
failure preserves the existing one-slot-per-engine fallback. No live provider load
test or authenticated production scan has been performed for this change.
Remaining: final server/client checks, final reviews, exact-SHA CI and release.
