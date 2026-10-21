# AIRate current project state

Updated 2026-10-21. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #80](https://github.com/egotrippingh/aiparser/pull/80),
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

- `codex/scan-persistent-retry`, based on production `c43a39f`: uncertain complete
  scans retry past three attempts with durable delays; accepted pending AI tasks
  yield workers and reuse their IDs. Existing exhausted tasks recover automatically.
- Projects have an empty searchable selector, no list-page sidebar and a scan
  progress column. Period/query dynamics compare actual first/last scan dates.
  Answer display cleans escaping/strong markup and makes source labels readable;
  Yandex sources use the common block. Original evidence and one user charge stay.
- Local132 frontend tests, lint/build, seven queue regressions and disposable
  desktop/narrow navigation/report/answer checks pass. Sol and Astra review passed;
  exact-SHA CI/production delivery are pending. No migration; pinned punycode2.3.1
  decodes IDN labels without a custom RFC decoder.

## Architecture and operating rules

- `server/`: FastAPI, PostgreSQL, all five managed providers, billing and recovery.
  `app/detect` is shared; historical device protocols/outbox remain compatible.
  Windows distribution and desktop UI/downloads are retired.
- `frontend/`: React/Vite; built assets in `web/`. Production is `https://airate.tech`;
  screenshots use Yandex S3 and semantic analysis uses OpenRouter.
- GitHub Actions deploys `production` with serialized activation, verified backups,
  isolated restore, migration admission, exact-SHA readiness and rollback.
- New checks cost165 kopeks per query/service; eligible recompute costs up to80 kopeks,
  failed analysis is uncharged. Clarification/recompute is gated to `ivoryya`.
- Email-code/Yandex registration and SMTP.BZ transactional mail are active.

## Open checks

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified; Aeza SMTP ticket is not rechecked.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Finish exact-SHA CI, then publish the authorized recovery/
project/report change through a production PR and verify Geosoft Dent completion.
Task scope: [scan recovery and reporting](docs/tasks/scan-recovery-projects-report.md).
