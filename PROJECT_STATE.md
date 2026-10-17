# AIRate current project state

Updated 2026-10-17. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #73](https://github.com/egotrippingh/aiparser/pull/73),
  release `58f0271958352e1ec05aa2e4bb4c7b4737e089b7`. Overview scan control,
  clockwise progress, calendar modes (up to 30 dates), consistent dropdowns and
  report-table controls/borders are live. All production gates, backup/isolated
  restore, activation and public readiness passed; live assets match the reviewed
  build. [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/38988130062).
- This includes PR #72: quick-start project video and `/docs/` guide routes.
  Previous cabinet/header, SEO, auth and deployment changes remain live.
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

- Prepared on `codex/brand-detection-quality`, not published: semantic identity routing,
  neutral arbiter, strict verdict validation, reserved-cache recovery and source-card
  evidence. Independent correctness/risk reviews found no remaining blocker; affected
  deterministic checks passed, full server gate is pending. No default model/price change.
  [24-case synthetic comparison](docs/brand-model-comparison.md): Qwen Flash is a candidate
  primary, DeepSeek Pro a candidate arbiter; real 90% precision/recall remains unverified.

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Finish server gates for prepared detection work, then obtain independent human holdout
labels and collector unit costs before model activation/publication. Keep existing
production backup, isolated restore, readiness and rollback gates.
