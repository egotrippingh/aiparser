# AIRate current project state

Updated 2026-10-20. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #78](https://github.com/egotrippingh/aiparser/pull/78),
  `7733f664a47413d3e3f0aa064394179498830a06`. Compact landing header and hero fill
  one dynamic viewport; no pause UI. Portrait/landscape Lottie art fits without cropping.
  125 frontend tests, lint/build, 12 viewport cases, guest/account menus, production
  CI, backup/isolated restore, exact readiness, four artwork hashes and ten entry
  assets passed. Live desktop/tablet/phone/landscape dimensions and console checked.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39386874879).
- Shared projects (#75), cabinet, documentation, SEO and auth remain included.

## Prepared work

- Prepared from production 7733f664: stable 100svh hero height replaces
  100dvh to prevent artwork rescaling with mobile browser bars. CSS-only;
  Lottie motion and responsive rotation remain. [Details](docs/landing-hero.md).
  Real-device Safari/Android rendering remains unverified.

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

Collect feedback on the published hero. Start subsequent changes from current
origin/production and preserve approved work; retain existing delivery gates.
