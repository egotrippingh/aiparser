# AIRate current project state

Updated 2026-10-19. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published: project IDs, email sharing, owner/editor/viewer rights and owner-funded
  editor scans, [PR #75](https://github.com/egotrippingh/aiparser/pull/75).
  Production CI and exact public readiness passed on 19 October.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39321679472),
  [migration and rollback](deploy/DELIVERY.md#project-sharing-schema-on-19-october-2026).
- Earlier cabinet, documentation, SEO, auth and deployment work remains included.

## Prepared work

- No unpublished application changes in this delivery. Sharing correctness/risk
  reviews, 383 server tests (including PostgreSQL races), 119 frontend tests,
  lint/build and disposable owner/editor/viewer desktop/mobile checks passed.
  [Scope and evidence](docs/project-access-task.md).

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

Collect real-user feedback on project sharing. Keep the compatible rollback image
and verified backup; continue the separate model/scan checks above.
