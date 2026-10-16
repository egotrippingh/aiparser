# AIRate current project state

Updated 2026-10-16. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #69](https://github.com/egotrippingh/aiparser/pull/69),
  release `5c9ac1aea27802ae2dd00ba61856d3fedae95080`. Parallel backend/frontend gates,
  cached Docker layers and reuse of the tested image are active. Existing backup,
  isolated restore, migration, readiness and rollback gates remain.
  [Deployment evidence](https://github.com/egotrippingh/aiparser/actions/runs/38939678649).
- Session-expiry fixes from PR #68 and retired desktop routes from PR #66 remain live.

## Prepared, not published

- `codex/homepage-seo`: homepage metadata/canonical/social cards and WebSite markup,
  build-time rendering, public robots/sitemap and utility-page noindex.
  [SEO policy and checks](docs/seo.md). Independent review found no blockers;
  final CI/deployment evidence will be recorded in the delivery PR.
- [PR #67](https://github.com/egotrippingh/aiparser/pull/67) contains separate workflow
  documentation/tooling improvements; it is outside the SEO release scope.

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

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Complete SEO CI, merge into `production`, then verify the exact live release and
public crawler responses. See [delivery](deploy/DELIVERY.md).
