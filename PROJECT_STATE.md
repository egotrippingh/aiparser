# AIRate current project state

Updated 2026-10-20. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #77](https://github.com/egotrippingh/aiparser/pull/77),
  `304260aa4d80145b1c0d68ac3a9914a60a5e7aff`. Responsive Lottie hero, original
  Figma artwork, texture-free mobile gradient, one CTA and static fallback.
  Production CI, backup/isolated restore, exact readiness, four artwork hashes,
  ten entry assets and live browser rendering passed.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39333805953).
- Shared projects (#75), cabinet, documentation, SEO and auth remain included.

## Prepared work

- Prepared on `codex/hero-viewport` from production `304260a`: remove pause UI,
  compact the landing header, and fit header + hero to one dynamic viewport.
  Portrait/landscape compositions fit the remaining height without cropping.
  [Implementation and checks](docs/landing-hero.md). Not yet published.

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

Deliver the requested viewport adjustment through a PR into production, then
verify the exact release and live layout. Retain existing delivery gates.
