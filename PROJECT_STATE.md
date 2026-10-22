# AIRate current project state

Updated 2026-10-22. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and live readiness verified: [PR #82](https://github.com/egotrippingh/aiparser/pull/82),
  release `73511701f89d0f93f3aa0cab91883d1eb1490833`. Mention dynamics use a common
  query/system/date base: 1/3 to 3/3 gives +66.7%, labelled % throughout. Missing
  AI blocks count as no mention; failures remain separate, with unknown percentages
  when no successful measurements exist. History uses the new formula on read.
- Saved-answer recompute is available to every project owner. The dashboard calendar
  supports from-date, one day, period, two dates, monthly and custom dates. Ownership,
  frozen run settings, quote selection and idempotent 80-kopeks billing are preserved.
- Independent Sol and Astra reviews passed after corrections. Exact-SHA PR and
  production CI passed: 415 server tests with PostgreSQL, 126 shared Python tests,
  136 frontend tests, lint/build, image smoke and proxy checks. Production delivery,
  backup/isolated restore and public readiness passed. Public help and cabinet bundle
  were verified externally; check pricing remains165. Disposable desktop/narrow UI
  covered success/failure, calendar modes, selected-date payloads, keyboard and console.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39758758357).
  Local evidence: `C:/codex-tmp/mention-growth-20261022` (synthetic data/fake AI).
- Published and live readiness verified: [PR #81](https://github.com/egotrippingh/aiparser/pull/81),
  release `33b8404dbe27081a7daeec13ee05eb3758281389`. Durable scan retries,
  project selector/progress and report/answer improvements are included.
- Previous tariff release: [PR #80](https://github.com/egotrippingh/aiparser/pull/80),
  release `c43a39f5805cd2aed2e25525af74c6875739c8ab`. New checks/server launches
  cost165 kopeks. Confirmed server runs/reservations preserve their price; stale
  quotes are rejected. Pause/top-up/manual-resume regression passes without
  repeated work/debits. Independent money review,385 server tests with PostgreSQL,
  125 frontend tests, lint/build and desktop/mobile quote UI passed. Production
  CI/deploy passed; live readiness, public pricing165 and absent container price
  override verified. Stable responsive Lottie hero remains included.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39407158649).
- Shared projects (#75), cabinet, documentation, SEO and auth remain included.

## Prepared work

- Admin checks and saved-answer recompute use a zero tariff, including wallet0
  with old paid reservations. Cabinet shows unlimited/free usage; ordinary billing
  and owner-only recompute remain intact. Sol and Astra reviews passed,35 focused
  API tests and137 frontend tests passed; lint/build and desktop/narrow fake-AI UI
  checks passed. Full local server/PostgreSQL and release CI are pending.
  Brief/evidence: `docs/tasks/admin-unlimited.md`; no schema/delivery change.

## Architecture and operating rules

- `server/`: FastAPI, PostgreSQL, all five managed providers, billing and recovery.
  `app/detect` is shared; historical device protocols/outbox remain compatible.
  Windows distribution and desktop UI/downloads are retired.
- `frontend/`: React/Vite; built assets in `web/`. Production is `https://airate.tech`;
  screenshots use Yandex S3 and semantic analysis uses OpenRouter.
- GitHub Actions deploys `production` with serialized activation, verified backups,
  isolated restore, migration admission, exact-SHA readiness and rollback.
- New checks cost165 kopeks per query/service; eligible recompute costs up to80 kopeks,
  failed analysis is uncharged. Clarification/recompute is available to every owner;
  shared viewers and device sessions cannot trigger it.
- Email-code/Yandex registration and SMTP.BZ transactional mail are active.

## Open checks

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified; Aeza SMTP ticket is not rechecked.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Mention-growth and recompute delivery is complete. Real paid/provider checks remain
outside the disposable acceptance run; do not trigger them without authorization.
Task scope: [mention dynamics and recompute](docs/tasks/mention-growth-recompute.md).
