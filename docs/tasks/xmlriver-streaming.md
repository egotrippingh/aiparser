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
- Stop/pause/shutdown block new paid calls and drain already-started responses/models.
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
Remaining: pipeline implementation, concurrency gates, reviews and release.
