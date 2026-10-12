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

Complete independent review and CI, including disposable PostgreSQL concurrency checks,
then create the combined production PR. Do not deploy the prepared branch directly.