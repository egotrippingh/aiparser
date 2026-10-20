# AIRate current project state

Updated 2026-10-20. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #79](https://github.com/egotrippingh/aiparser/pull/79),
  `80d6415e79096b371c208bf572878ccdb28f2728`. Stable `100svh` prevents hero
  rescaling with mobile browser bars. Lottie, compact header and responsive
  rotation remain. 125 frontend tests, lint/build, four viewport/scroll cases,
  PR and production CI passed. Live readiness, stable CSS rule, mobile Lottie,
  scroll dimensions and console checked.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/39390857829).
- Shared projects (#75), cabinet, documentation, SEO and auth remain included.

## Prepared work

- Tariff update prepared from production `80d6415`: new checks/server runs cost
  165 kopeks. Confirmed server runs and reservations keep their price; stale quotes
  are rejected. Pause/top-up/manual-resume regression passes, including insufficient
  164 and exact 165, no repeated work/debits. Independent money review passed.
  125 frontend tests, lint/build and desktop/mobile quote UI passed; full server
  suite and delivery are pending. Install protected VPS env/Compose tariff before
  activation and verify live pricing165. No migration or recompute80 change.

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

Collect feedback on mobile scrolling from a physical phone. Start subsequent changes from current
origin/production and preserve approved work; retain existing delivery gates.
