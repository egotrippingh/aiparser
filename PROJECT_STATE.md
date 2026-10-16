# AIRate current project state

Updated 2026-10-16. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Published and verified 2026-10-16: [PR #68](https://github.com/egotrippingh/aiparser/pull/68), release `cbb9d522b3cd7acc050709caba444680d96bb9aa`. Expired sessions show one login notice; current-password rejection and stale responses after cookie rotation are covered. 103 frontend tests, 403 server/support tests, independent reviews, disposable browser check, isolated backup restore, exact live readiness and six JS/CSS asset hashes passed. Existing user sessions were not forcibly expired for live testing. [Deployment evidence](https://github.com/egotrippingh/aiparser/actions/runs/38937559238).

- Published and verified: [PR #66](https://github.com/egotrippingh/aiparser/pull/66),
  release `28972c5157e5c1fd0123703d07db5d993f8a93f7`; schema unchanged
  (`20261015_email_registration`). Desktop UI/downloads retired; icon navigation,
  separate All Projects button and searchable project chooser are live.
  Recorded release evidence: CI, isolated backup restore, exact readiness/assets,
  retired routes, local signed-in smoke and live guest smoke. Signed-in live smoke
  for #66 remains unverified. Details: [release history](docs/project-state-history-2026-10-16.md).

## Prepared, not published

- Workflow improvements: [PR #67](https://github.com/egotrippingh/aiparser/pull/67),
  `codex/workflow-efficiency`, updates preview/approval rules,
  scoped checks, task acceptance lists, Graphify provenance and on-demand release status.
  17 deterministic checks and independent review passed; current CI evidence is in
  the PR. This is developer tooling/documentation; no application release is authorized here.

## Architecture and operating rules

- Server runs all five providers. `server/`: FastAPI, PostgreSQL, managed runs,
  billing and recovery; `app/detect` is shared detection code. Historical device
  protocols/outbox remain for compatibility; Windows distribution is retired.
- `frontend/`: React/Vite; tracked site assets in `web/`. Production:
  `https://airate.tech`; Yandex S3 screenshots, OpenRouter semantic analysis.
- GitHub Actions deploys `production` with serialized activation, backup/isolated
  restore, migration gates, exact-SHA readiness and rollback. `main` is development.
- Checks cost 120 kopeks per query/service; saved-answer recompute up to 80 kopeks
  per eligible answer, failed analysis uncharged. Clarification/recompute remain
  gated to the exact `ivoryya` admin. No AI block means a check without a mention;
  technical errors stay outside the denominator. No automatic query retry.
- Email-code/Yandex registration and account selection are live. SMTP.BZ sends
  registration/recovery/top-up mail; REG.RU mail/DNS are retained. See
  [registration](docs/registration-email.md) and [top-up mail](docs/topup-emails.md).

## Open checks

- Real clarification scan, historical S3 recovery, paid recompute and live PostgreSQL
  upload/recompute race remain unverified. First real paid top-up email and signed-in
  multi-account Yandex choice remain unverified; Aéza SMTP ticket is not rechecked.
- An off-VPS database backup destination is not confirmed; current backups are VPS-local.

## Next action

Before merging PR #67, synchronize its base and release facts with the separately
authorized [session-expiry release #68](https://github.com/egotrippingh/aiparser/pull/68).

Use [delivery](deploy/DELIVERY.md), [workflow](docs/agent-workflow.md) and
`python scripts/release_status.py` when release state matters. Read historical
evidence only for a specific investigation; update facts here instead of appending logs.
