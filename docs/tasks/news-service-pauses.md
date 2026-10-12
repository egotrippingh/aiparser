# News, provider pauses and sparse charts

Base: `1965d37`; branch `codex/news-service-pauses`.

Outcome: public `/news/` renders plain text and emoji without a login. Only an
administrator can publish. Administrators can pause each of five server
providers; unadmitted work is durably skipped, submitted work drains once, and
scheduled all-paused occurrences are consumed rather than replayed.

Scope: `NewsPost`, additive migration, provider account pause marker, admission,
cloud completion, control scheduling, private admin controls, public frontend,
chart timeline, delivery CI and generated `web/`.

Keep: owner/admin/device boundaries, Origin/CSRF session behaviour, frozen runs,
saved captures, once-only payment settlement, rollback/backup gates and historical
results. No news edit/delete and no provider calls in checks.

Acceptance:
- anonymous feed is cursor-bounded, newest-first and excludes author details;
  body is length-bounded plain text rendered by React;
- anonymous, ordinary and device sessions cannot publish or alter provider state;
- a paused service cannot admit new work; a later resume cannot revive a pair
  that was pending when the pause occurred;
- submitted task IDs continue to poll/save/settle; skipped pairs make the run
  terminal without report error rows or a charge;
- a healthy provider can continue and paused-only schedules do not backlog;
- chart omits calendar-only dates and any dashed interpolation, preserving zero;
- Windows agent workflow and CI-only desktop steps are retired, while server,
  shared parser/rules/XML and frontend checks remain.

Delivered on 2026-10-12 through PR #51, with separate renderer PR #52. Production
`62536ba7389fd625656155b48ec77ddb99823ddc`; Actions run 38295211655 attempt 2 passed.
Evidence: 194 server tests with disposable PostgreSQL, 66 retained shared checks
without the retired browser runtime, 83 frontend tests, lint/build and generated
web, independent Sol/Astra reviews, desktop/390px fixture checks and live asset
and exact-release readiness checks. Existing desktop assertions remain in manual
legacy test files.

Operator preparation verified the backup checksum, migrated an isolated restored
copy twice, compared all previous columns/records and started both candidate and
compatible rollback in production mode. Graceful activation repeated the final
backup and preservation check before readiness; the normal backup/restore/deploy
gates then passed. Compatible image: `airate-web:news-rollback-62536ba7389f`, ID
`sha256:a99092ac04334a32a0bfda9bd96056bf58b2172cd7aa30518a6c1f8914bb96c2`.
Private fingerprints and backup details remain in root-only release evidence on
the VPS. No paid scans or real production posts were launched for verification.

Deployment note: this revision is additive (new table and defaulted columns), but
the existing runtime refuses a database ahead of its Alembic head. Deploy with the
prepared schema-compatible rollback image and the normal backup/isolated restore
gate; do not roll back to the old startup metadata after migration.
