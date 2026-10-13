# AIRate current project state

## Current release

Production is `62536ba`, verified on 2026-10-12 after PRs #51/#52 (deploy run
38295211655, attempt 2). Backup, restore, migration-head and exact-SHA readiness
gates passed. Previous records were verified unchanged during migration. Historical
release evidence is in [project-state-history-2026-10-12.md](docs/project-state-history-2026-10-12.md).

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

`codex/telegram-news` prepares replacement of the web feed with a Telegram news
link in website/cabinet headers. Feed page/API and admin composer are removed
in the draft; stored posts and migration head are preserved. Admin tests (5),
frontend tests (83), lint/build and Graphify update passed. The news link uses
`https://t.me/airtate_tech`; complete browser checks, Docker refresh, CI and deployment.
This replacement is unpublished; production and Docker still use the prior release.

The full server suite passed with disposable
PostgreSQL (194 tests); retained shared CI checks passed without the retired browser
runtime (66 tests). Independent review and production activation are complete.
Local Docker preview is running at `http://127.0.0.1:8795` with disposable data,
disabled scan workers and no production credentials. No pending release checks.
## Delivered answer display

PR #52 renders reference citations, removes synthetic answer tiles
and suppresses duplicate source footers. Its 83 frontend tests, lint/build and
desktop/mobile fixture checks passed. Both changes are deployed in the same release.
See [answer-display.md](docs/tasks/answer-display.md).
