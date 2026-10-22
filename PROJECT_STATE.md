# AIRate current project state

Updated 2026-10-22. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and live verified: [PR #85](https://github.com/egotrippingh/aiparser/pull/85),
  release `c21633d347f922f4da4ded5e0d23764b8589636d`. XMLRiver failures now retain
  safe timeout/network/HTTP/API/malformed/incomplete/cancellation diagnostics in the
  bounded task history. Retry timing, provider budgets and billing are unchanged.
- Independent correctness/risk review passed. Exact-SHA CI passed 423 PostgreSQL
  server tests, shared checks, 137 frontend tests, lint/build and image smoke.
  Backup/isolated restore, public readiness and installed diagnostic smoke passed.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39821835936).
  Live ordinary-attempt diagnostics verified: API500 and incomplete/missing_content;
  two user-authorized diagnostic requests confirmed empty AI content, then API500;
  the second full XML was saved outside Git and its transfer hash verified.
- Included: unlimited/free admin checks (#83), owner-only saved-answer recompute
  and common-base mention dynamics (#82), durable scan recovery/report UI (#81),
  tariff165/frozen run prices (#80), shared projects, cabinet, SEO and auth.

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

## Prepared work and next action

`codex/xmlriver-retry-recovery` adds a bounded Yandex raw-page fallback after
API500 or incomplete XML, using the existing request budget and durable save path.
Independent correctness review passed; final risk review and delivery CI pending.
A genuine Triol answer is saved privately for fenced recovery through the worker;
terminal completion remains unverified. See [task evidence](docs/xmlriver-retry-recovery.md).
Delivery checkout: `C:/Users/ego/.codex/worktrees/provider-failure-diagnostics/aiparser`.