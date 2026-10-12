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

Evidence: focused admin/news, cloud pause and chart tests; full server suite with
the disposable PostgreSQL URL, frontend test/lint/build, generated web and review
remain before the production PR.

Deployment note: this revision is additive (new table and defaulted columns), but
the existing runtime refuses a database ahead of its Alembic head. Deploy with the
prepared schema-compatible rollback image and the normal backup/isolated restore
gate; do not roll back to the old startup metadata after migration.
