# AIRate current project state

Updated 2026-10-22. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

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

- `codex/mention-growth`, based on production `33b8404`: a common query/system/date
  base fixes mention dynamics; 1/3 to3/3 gives +66.7%, labelled% throughout.
  Missing AI blocks count as no mention. Errors remain separate; no successful
  measurements means unknown. Existing frozen runs retain their feature settings.
- Saved-answer recompute is available to every project owner, with the shared
  dashboard calendar: from a date, single day, period, two dates, monthly and custom
  dates. Quote/POST share selection validation, ownership and idempotent billing.
- Independent Sol and Astra reviews passed after corrections. Full server run:
  418 passed and one stale help-copy expectation failed; that expectation was
  updated for the agreed formula and all16 SEO tests passed. PostgreSQL tests
  used an isolated local cluster. Shared CI checks126 passed; frontend136 tests,
  lint and build passed. Disposable desktop/narrow UI checked success/failure,
  calendar modes, keyboard, console and exact selected-date POST payloads.
- No schema/delivery changes. Exact-SHA GitHub CI and deployment are pending login.
  Logs and synthetic UI evidence: `C:/codex-tmp/mention-growth-20261022`.

## Architecture and operating rules

- `server/`: FastAPI, PostgreSQL, all five managed providers, billing and recovery.
  `app/detect` is shared; historical device protocols/outbox remain compatible.
  Windows distribution and desktop UI/downloads are retired.
- `frontend/`: React/Vite; built assets in `web/`. Production is `https://airate.tech`;
  screenshots use Yandex S3 and semantic analysis uses OpenRouter.
- GitHub Actions deploys `production` with serialized activation, verified backups,
  isolated restore, migration admission, exact-SHA readiness and rollback.
- New checks cost165 kopeks per query/service; eligible recompute costs up to80 kopeks,
  failed analysis is uncharged. Live33b8404 gates clarification/recompute to `ivoryya`;
  the prepared mention-growth change opens it to every owner.
- Email-code/Yandex registration and SMTP.BZ transactional mail are active.

## Open checks

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified; Aeza SMTP ticket is not rechecked.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Finish GitHub CLI login, create a production PR for mention-growth, verify its CI,
publish the authorized change and verify live readiness against the release SHA.
Task scope: [mention dynamics and recompute](docs/tasks/mention-growth-recompute.md).
