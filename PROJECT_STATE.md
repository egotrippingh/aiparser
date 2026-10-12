# AIRate current project state

## Current release

Production is `1965d37`, verified on 2026-10-12 after PRs #49/#50 (deploy run
38273933574). Backup, restore, migration-head and readiness gates passed. Historical
release evidence is in [project-state-history-2026-10-12.md](docs/project-state-history-2026-10-12.md).

## Prepared change

`codex/news-service-pauses` adds public news, admin-only publishing, provider pause
admission controls and sparse actual-scan chart dates. Migration
`20261012_news_provider_pauses` is additive. The change is prepared and unpublished;
the compatibility runtime must accompany any application rollback after migration.
See [news-service-pauses.md](docs/tasks/news-service-pauses.md).

## Architecture

`server/` owns accounts, runs, billing and cloud collection; `frontend/` builds the
tracked `web/` interface. Production delivery retains CI, backup/restore, migration
checks, readiness and rollback gates.

## Open checks and next action

PR #51 contains the first feature. The full server suite passed with disposable
PostgreSQL (194 tests); retained shared CI checks passed without the retired browser
runtime (66 tests). Complete renderer review and stacked PR, then combined CI,
restored-copy migration/rollback verification and production activation.
## Prepared answer display

`codex/answer-display` renders reference citations, removes synthetic answer tiles
and suppresses duplicate source footers. Its 83 frontend tests, lint/build and
desktop/mobile fixture checks passed. Both changes await the same production
activation. See [answer-display.md](docs/tasks/answer-display.md).
