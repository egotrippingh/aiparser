# AIRate current project state

Updated 2026-10-22. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and live readiness verified: [PR #83](https://github.com/egotrippingh/aiparser/pull/83),
  release `d711aead8d1759309e660e09987bc039f5649e2c`. Admin checks and saved-answer
  recompute are free, including wallet0 with old paid reservations. Cabinet shows
  unlimited/free usage. Ordinary billing, existing reservations, ownership and
  idempotency remain intact; no schema/delivery changes.
- Sol and Astra reviews passed. Local422 server tests with disposable PostgreSQL,
  137 frontend tests, lint/build and desktop/narrow fake-AI UI passed. Exact-SHA PR
  and production CI passed:418 server tests,126 shared Python tests,137 frontend,
  image/proxy and delivery gates. Backup/isolated restore and public readiness passed.
  Live cabinet bundle matches the tested build; public check pricing remains165.
  Read-only verification confirmed one admin account with recent check prices0.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39766813237).
  Local evidence: `C:/codex-tmp/admin-unlimited-20261022` (synthetic data/fake AI).
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

- Admin-unlimited delivery is complete. Brief/evidence:
  `docs/tasks/admin-unlimited.md`; no unfinished implementation.

## Architecture and operating rules

- `server/`: FastAPI, PostgreSQL, all five managed providers, billing and recovery.
  `app/detect` is shared; historical device protocols/outbox remain compatible.
  Windows distribution and desktop UI/downloads are retired.
- `frontend/`: React/Vite; built assets in `web/`. Production is `https://airate.tech`;
  screenshots use Yandex S3 and semantic analysis uses OpenRouter.
- GitHub Actions deploys `production` with serialized activation, verified backups,
  isolated restore, migration admission, exact-SHA readiness and rollback.
- Ordinary accounts: new checks cost165 kopeks per query/service; eligible recompute
  costs up to80 kopeks, failed analysis is uncharged. Admin checks/recompute are free.
  Clarification/recompute is available to every owner;
  shared viewers and device sessions cannot trigger it.
- Email-code/Yandex registration and SMTP.BZ transactional mail are active.

## Open checks

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified; Aeza SMTP ticket is not rechecked.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Mention-growth, recompute and admin-unlimited delivery is complete. Real paid/provider checks remain
outside the disposable acceptance run; do not trigger them without authorization.
Task scope: [admin unlimited](docs/tasks/admin-unlimited.md),
[mention dynamics and recompute](docs/tasks/mention-growth-recompute.md).
