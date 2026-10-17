# AIRate current project state

Updated 2026-10-16. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified: [PR #71](https://github.com/egotrippingh/aiparser/pull/71),
  release `203a6023a8f4e1acc59181a89e57176abff48b75`. Cabinet header styling,
  email support and eight public Fumadocs guides/search are live. Full production
  CI, backup/isolated restore and activation passed; live readiness matches SHA.
  Eight articles, 11 assets, sitemap and live browser search passed smoke checks.
  [Delivery evidence](https://github.com/egotrippingh/aiparser/actions/runs/38952970914).
- Published and readiness verified: [PR #70](https://github.com/egotrippingh/aiparser/pull/70),
  release `8a37da3cc1b3f40947dd7587ed8f553ceab7f787`. Homepage metadata, canonical/social
  cards, WebSite markup, build-time rendering, robots/sitemap and utility-page noindex.
  [Deployment evidence](https://github.com/egotrippingh/aiparser/actions/runs/38941999184).
  [SEO policy and checks](docs/seo.md). Actual search indexing remains unverified.
- Published and verified: [PR #69](https://github.com/egotrippingh/aiparser/pull/69),
  release `5c9ac1aea27802ae2dd00ba61856d3fedae95080`. Parallel backend/frontend gates,
  cached Docker layers and reuse of the tested image are active. Existing backup,
  isolated restore, migration, readiness and rollback gates remain.
- Session-expiry fixes from PR #68 and retired desktop routes from PR #66 remain live.
- `production` also includes [PR #67](https://github.com/egotrippingh/aiparser/pull/67)
  at `0a80911`: preview/scoped-check rules, Graphify provenance and the on-demand
  release-status script; its production CI/readiness passed before PR #71 delivery.

## Prepared, not published

- `codex/help-video`: user-provided project-creation video below «Создайте проект»
  in the quick-start article; click/keyboard play-pause and custom seek slider,
  without native controls. Public guides move to `/docs/`, header/footer label
  «Документация»; old `/help/` URLs permanently redirect to matching pages.
  Local checks passed (115 frontend tests, lint/build, 16 SEO/HTTP tests), browser
  route/search/video/header checks and independent source/risk review passed.
  PR #72 CI and publication pending. Base: production `203a602`.

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

- Prepared, not published: `codex/overview-calendar-preview`, based on production
  `29114ed07637e7c9d9357a5ad638ef668bc259e4`. Compact scan control, chart-only service
  selection and calendar modes with up to 30 dates; no Yandex-update markers.
  Active ring has no number or click action; progress stays in its tooltip.
  Interactive disposable-data preview awaits user feedback. No real scans or charges.

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Next action

Review the overview/calendar preview with the user, incorporate feedback, then complete
delivery gates and release only with publication authorization.
