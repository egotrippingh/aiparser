# AIRate current project state

Updated 2026-10-18. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

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
  deterministic checks passed. Full server/CI evidence is tracked in
  [draft PR #74](https://github.com/egotrippingh/aiparser/pull/74).
  Full source CI on `4da1a05` passed. [300-answer blind audit](docs/brand-model-audit.md):
  Qwen 294/300 valid, Pro 288/300; 282/283 complete decisions agree, not an accuracy score.
  Shared experiment cost upper bound $0.72401 under $5. No default model/price change.
  [First human pilot](docs/brand-human-pilot.md): 21 saved labels, all resolved after one explicit
  human adjudication. Qwen agrees 21/21; Pro 20/21 including one connection failure. No semantic mistake
  among returned decisions yet; 90% remains unconfirmed. Private web review continues.

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Await further independent human labels, including hard cases and new brands,
then recompute metrics. The first 21 labels are imported without changing verdicts or
running paid calls. Model activation/publication remains pending; confirm collector
costs and retain production backup, isolated restore, readiness and rollback gates.
