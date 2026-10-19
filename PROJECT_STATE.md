# AIRate current project state

Updated 2026-10-20. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and readiness verified: [PR #75](https://github.com/egotrippingh/aiparser/pull/75),
  `08053d4fcd4aa26d95952c2adb8ba23b44ff06a8`. Production CI and exact public
  readiness match. Shared projects, owner/editor/viewer roles and owner-funded
  scans are included. [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39321679472).
- Earlier cabinet, documentation, SEO, auth and deployment work remains included.

## Prepared work

- Approved responsive Lottie hero implemented in `codex/landing-lottie`, not yet
  published. Original Figma artwork, mobile background without texture, one CTA,
  12-second scan/data/report loop, pause and reduced-motion fallback.
  125 frontend tests, lint/build and independent review passed.
  [Implementation and checks](docs/landing-hero.md).

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

Deliver the approved responsive hero through a reviewed PR into production, then
verify exact public readiness and artwork assets. Publication is authorized for
this hero. Retain backup, isolated restore, migration and rollback gates.
