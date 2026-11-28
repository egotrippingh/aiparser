# AIRate current project state

Updated 2026-11-21. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Prepared locally on 2026-11-28

- `codex/airate-competitor-citations`, includes production redesign `a2bbe63`, adds a tracked
  competitor roster, mention counts and brand gaps, plus exact cited pages and their
  saved answers. Both reports use project history without a scan or database migration.
- The local preview and Playwright test use disposable accounts and SQLite.
  Edge E2E passed for the owner and viewer, with layout checks at 320, 390 and 1440 px.
  Reproduce with [the E2E runner](scripts/e2e_project_analysis.py) after building the frontend.
  Release remains pending.
- The desktop navigation expands over the report after 400 ms of hover, with a lightly translucent background.
  Source-link previews stay aligned when moving quickly between links.
- The visibility overview labels previous-period and between-scan comparisons separately.
- The signed-in homepage and cabinet share the compact header and 28 px avatar.
- Public pages and cabinet share the thin native scrollbar style.

## Current release

- Published and live verified: [PR #99](https://github.com/egotrippingh/aiparser/pull/99),
  release `a88af391c37f61b3a4c83d22a90a2af7932c36d7`. Includes the dark
  SCSS/BEM design, cabinet refinements, PDF/DOCX client reports from PR #97,
  and optional Yandex ID avatars.
- PostgreSQL is at `20261121_yandex_avatar`. Migration and application rollback
  passed on an isolated restore. A fresh production backup was restored separately,
  and fingerprints of all pre-existing columns matched before and after migration.
  The previous release's schema-compatible image is `airate-web:avatar-compat-5948bfee`.
- [Production CI and deploy](https://github.com/egotrippingh/aiparser/actions/runs/44915058722)
  passed, including checksum and backup restore. Live readiness matched the release.
  Homepage, docs, HTTP 404, cabinet assets, PDF/DOCX modules and the optional
  Yandex scope were verified.

## Prepared admin console

- `codex/admin-subdomain`, based on production `d3307c0`, contains a separate
  operator console with isolated sessions, existing administration, a shared
  run journal, wallet totals and provider budgets. No schema change.
- The forecast combines scheduled and outstanding checks, actual recorded
  OpenRouter usage, recent manual pace and calibrated collector rates.
  Production rollout follows preview approval and DNS/TLS setup.
  [Rollout sequence](deploy/DELIVERY.md#admin-console-rollout).

## Architecture and operating rules

- `server/`: FastAPI, PostgreSQL, all five managed providers, billing and recovery.
  `app/detect` is shared; historical device protocols/outbox remain compatible.
  Windows distribution and desktop UI/downloads are retired.
- `frontend/`: React/Vite; built assets in `web/`. Production is `https://airate.tech`;
  screenshots use Yandex S3 and semantic analysis uses OpenRouter.
- GitHub Actions deploys `production` with serialized activation, verified backups,
  isolated restore, migration admission, exact-SHA readiness and rollback.
- New checks cost165 kopeks per query/service; eligible recompute costs up to80 kopeks,
  failed analysis is uncharged. Clarification/recompute is available to every owner;
  shared viewers and device sessions cannot trigger it.
- Email-code/Yandex registration and SMTP.BZ transactional mail are active.

## Open checks

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified; Aeza SMTP ticket is not rechecked.
- Live Yandex ID reauthorization with avatar consent remains unverified.
- Off-VPS database backups are not confirmed; existing backups are VPS-local.
- Search Console/Yandex Webmaster submission and actual indexing are not verified.

## Prepared work and next action

`codex/airate-mcp-site` is based on production `a88af39` and includes the MCP
tools from PR #98 in a Node.js package, separate REST API and MCP sections on
the homepage, and setup guides for seven clients. The website build packages
MCP as a versioned npm tarball. Next step is owner approval of the preview,
then delivery CI and release.

`codex/admin-wallet-topups` is based on production `f767a44`. The admin
users section supports manual balance credits by email. Credits use the
existing wallet and ledger transaction with retry protection and require no
migration. Independent frontend and money/auth reviews, 8 admin tests with
disposable PostgreSQL, 143 frontend tests, lint/build and desktop/narrow
browser checks passed. Next step is delivery CI before a production release.

`codex/metrika-114026759`, based on production `709807b`, installs the supplied
Yandex Metrika counter114026759 on public, legal and documentation HTML entries.
Local counter checks cover asynchronous loading, init options and duplicate-tag
protection. The cabinet is excluded to protect auth secrets and private reports;
the public account header is masked from replay/click/link tracking. The privacy
policy describes public-page analytics.
Deployment/live evidence belongs in [PR #94](https://github.com/egotrippingh/aiparser/pull/94).

`codex/xmlriver-retry-recovery` adds a bounded Yandex raw-page fallback after
API500 or incomplete XML, using the existing request budget and durable save path.
Independent correctness review passed; final risk review and delivery CI pending.
A genuine Triol answer is saved privately for fenced recovery through the worker;
terminal completion remains unverified. See [task evidence](docs/xmlriver-retry-recovery.md).
Delivery checkout: `C:/Users/ego/.codex/worktrees/provider-failure-diagnostics/aiparser`.
