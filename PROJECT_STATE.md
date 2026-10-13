# AIRate current project state

## Provider queue isolation (2026-10-13, deployed)

Branch codex/provider-isolation removes account-wide pauses for individual unknown
Scrapeless sends and XML transient failures, while preserving occupied slots,
global auth/quota guards and ambiguous-POST no-resend. XML network exhaustion is
classified as a retryable query failure. No schema or frontend change.
Five regressions failed before the fix; focused provider/XML96 and shared67 pass
with disposable PostgreSQL. Final full server243 passed; Sol/Astra reviews passed.
Full-capacity regression covers slot reuse in the same tick. PR56 merged after
exact-head CI38384826583 passed. Production CI38385385962 passed;
HTTPS readiness confirms67575132d4f4d3b0852fc9c62bd7e5fdbb2f8aab and pricing120.
Live geosoft-dent: ChatGPT121 ->301 of303, Yandex186 ->203 of303 after activation.
One pre-existing uncertain POST is retained without resend; one expired handle
and the remaining Yandex tail still require normal recovery/provider responses.
See [provider-isolation.md](docs/tasks/provider-isolation.md).

## Automatic collection recovery and report filters (2026-10-13)

PR #55 recovers new complete-policy empty/failed/expired tasks automatically;
an expired handle is rechecked before another paid submission. Deferred tasks
leave free provider slots usable, with bounded admission and durable shared cooldowns.
Original completed history and one wallet settlement per Check are preserved.
Reports expose independent external-source/product-card switches; own-domain mode
uses safe HTTP(S) sources consistently across charts, totals, tables and XLSX.
Final full server: 229 passed with disposable PostgreSQL; frontend84/lint/build,
XMLRiver27 and desktop/mobile keyboard QA passed. Sol/Astra reviews completed.
PR CI 38372134424 and production CI 38372769409 succeeded. No schema change.
Live geosoft-dent scan advanced from 576 to706 of1212 after activation.
Evidence: C:/codex-tmp/airate-recheck-qa/; [collection-recheck.md](docs/tasks/collection-recheck.md).

## Monthly calendar completion (2026-10-13)

Branch codex/schedule-calendar starts from production b165c429dc94b3de312072ec8cfa60f334723cc8
and preserves PRs #49–53. Server last_day support and actual-scan chart dates are
already published; the remaining UI now offers 1–28 and the last-day flag, including
last-day-only schedules, explicit legacy 29–31 removal and complete schedule labels.
84 frontend checks, lint/build, 8 schedule regressions and desktop/390px disposable
browser checks passed; independent Sol review found no blockers. No schema change.
Evidence: C:/codex-tmp/airate-schedule-calendar-20261013/; task
[scan-calendar-days.md](docs/tasks/scan-calendar-days.md).
PR #54 is merged into production 99d7fb34584eb9b12dab1378d7b73960fe4a86a5.
PR CI 38357093941 passed; production CI 38357731853 passed Tests and build and
Upload and activate verified release, then failed Verify public release.
After email confirmation, Radix RDAP no longer reports client hold and Google DNS
resolves the domain to 45.146.90.88. Normal HTTPS public verification passed on
2026-10-13: exact release SHA, pricing, 12 matching assets and anonymous private
routes returning 401. The original failed CI run remains historical; no gate was bypassed.

## Current release

Production is `ddec8319283954deafe3b9d0d3e0691b84b4e539` from PR #55.
Normal HTTPS verification confirms the exact SHA, pricing, 12 matching public assets
and anonymous private routes returning401. Production CI and readiness passed.
Previous records were verified unchanged during the PR #51/#52 migration.
Historical release evidence is in
[project-state-history-2026-10-12.md](docs/project-state-history-2026-10-12.md).

## Delivered change

PR #51 delivers public news, admin-only publishing, provider pause
admission controls and sparse actual-scan chart dates. Migration
`20261012_news_provider_pauses` is live and additive. Application rollback requires
`airate-web:news-rollback-62536ba7389f`, verified against the restored migrated DB;
the old application image cannot start against this schema.
See [news-service-pauses.md](docs/tasks/news-service-pauses.md).

## Architecture

`server/` owns accounts, runs, billing and cloud collection; `frontend/` builds the
tracked `web/` interface. Production delivery retains CI, backup/restore, migration
checks, readiness and rollback gates.

## Open checks and next action

Geosoft-dent remains in progress; complete-run live verification is still pending.
An automatic provider retry can spend provider balance again; the client Check
settles once. No live new scan/payment was initiated for QA. The disposable
PostgreSQL instance and report QA server started for these checks are stopped.
## Delivered answer display

PR #52 renders reference citations, removes synthetic answer tiles
and suppresses duplicate source footers. Its 83 frontend tests, lint/build and
desktop/mobile fixture checks passed. Both changes are deployed in the same release.
See [answer-display.md](docs/tasks/answer-display.md).
