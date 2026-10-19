# AIRate current project state

Updated 2026-10-19. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published source: [PR #74](https://github.com/egotrippingh/aiparser/pull/74),
  `112cd86b7133c30a32938dc5d0ae0320165687d4`. Production CI and exact public
  readiness matched on 19 October. Runtime model overrides were not rechecked.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39162386180).
- Earlier cabinet, documentation, SEO, auth and deployment work remains included.

## Prepared work

- [PR #75](https://github.com/egotrippingh/aiparser/pull/75): permanent visible project IDs; owner-managed email sharing,
  editor/viewer roles and owner-funded editor scans. Not published. Independent
  correctness/risk reviews are clear. Frontend 119 tests, lint/build and disposable
  owner/editor/viewer desktop/mobile checks passed; backend/PG gates are tracked in the PR.
  Additive head `20261019_project_members` requires reviewed migration admission
  and a compatible rollback image before publication. [Scope and gates](docs/project-access-task.md).

## Architecture and operating rules

- `server/`: FastAPI, PostgreSQL, all five managed providers, billing and recovery.
  `app/detect` is shared; historical device protocols/outbox remain compatible.
  Windows distribution and desktop UI/downloads are retired.
- `frontend/`: React/Vite; built assets in `web/`. Production is `https://airate.tech`;
  screenshots use Yandex S3 and semantic analysis uses OpenRouter.
- GitHub Actions deploys `production` with serialized activation, verified backups,
  isolated restore, migration admission, exact-SHA readiness and rollback.
- Checks cost 120 kopeks per query/service; eligible recompute costs up to 80 kopeks,
  failed analysis is uncharged. Clarification/recompute is gated to `ivoryya`.
- Email-code/Yandex registration and SMTP.BZ transactional mail are active.

## Open checks

- Model source rollout is published; installed Compose/model overrides still need
  confirmation. Human accuracy target of 90% remains unconfirmed; continue labels
  separately. Approved Qwen primary / Pro-none arbiter, unchanged tariff and no
  per-check monetary cutoff remain. Evidence: [model audit](docs/brand-model-audit.md),
  [human pilot](docs/brand-human-pilot.md), [isolated scan](docs/brand-route-scan.md).

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Review the project-access PR and disposable interactive preview, then collect UI/release
approval. Retain production backup, isolated restore, migration
admission, readiness and rollback gates; do not publish without separate approval.
