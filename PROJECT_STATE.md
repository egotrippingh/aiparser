# AIRate current project state

Updated 2026-11-21. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published: [PR #96](https://github.com/egotrippingh/aiparser/pull/96), release
  `5948bfee2b80402f8243e6aaf19ef45f0b9ffa34`. The release adds account-key REST
  integration, project removal in the cabinet and scan recovery changes.
- [Exact-SHA CI and deployment](https://github.com/egotrippingh/aiparser/actions/runs/44515913170)
  passed. On 2026-11-21 public readiness reported that SHA and the public project
  list returned HTTP 401 without a key.

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

`codex/airate-mcp` adds a local stdio adapter for the public REST API. The
[MCP guide](docs/airate-mcp.md) covers client setup and the required update when
the public REST contract changes. The next action is PR review.
