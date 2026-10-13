# AIRate current project state

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
DNS returns NXDOMAIN; Radix RDAP confirms client hold (expiry 2027-09-27).
REG.RU hold removal and final public verification remain; no gate was bypassed.

## Current release

Production activation is `99d7fb3` from PR #54 on 2026-10-13; its public check failed
because the domain is held. The last fully verified public release is `62536ba`,
after PRs #51/#52 (deploy run 38295211655, attempt 2). Backup, restore, migration-head
and exact-SHA readiness gates passed then. Previous records were verified unchanged
during migration. Historical release evidence is in
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

PR #53 merged the Telegram news replacement into production b165c429dc94b3de312072ec8cfa60f334723cc8.
The news link is https://t.me/airtate_tech; stored posts and migration head remain.
Its production activation passed; the final external verification failed resolving
the public domain. The prior local Docker preview is not current release evidence.

The full server suite passed with disposable
PostgreSQL (194 tests); retained shared CI checks passed without the retired browser
runtime (66 tests). Independent review and production activation are complete.
The prior local Docker preview at `http://127.0.0.1:8795` used disposable data,
disabled scan workers and no production credentials; its current state is unverified.
The calendar QA fixture was stopped. Public verification remains pending domain recovery.
## Delivered answer display

PR #52 renders reference citations, removes synthetic answer tiles
and suppresses duplicate source footers. Its 83 frontend tests, lint/build and
desktop/mobile fixture checks passed. Both changes are deployed in the same release.
See [answer-display.md](docs/tasks/answer-display.md).
