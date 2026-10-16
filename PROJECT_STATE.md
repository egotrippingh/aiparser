# AIRate current project state

Updated 2026-10-16. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Published

- Published and verified: [PR #66](https://github.com/egotrippingh/aiparser/pull/66),
  release `28972c5157e5c1fd0123703d07db5d993f8a93f7`; schema unchanged
  (`20261015_email_registration`). Desktop UI/downloads retired; icon navigation,
  separate All Projects button and searchable project chooser are live.
  Recorded release evidence: CI, isolated backup restore, exact readiness/assets,
  retired routes, local signed-in smoke and live guest smoke. Signed-in live smoke
  for #66 remains unverified. Details: [release history](docs/project-state-history-2026-10-16.md).

## Prepared, not published

- Session-expiry notice fix: `619ac9c9038d4a6e69ea3b613f7d834bf5f65bfd` on development
  `main`; 81 frontend tests, lint/build, disposable browser check and focused review
  recorded. Source: `codex/session-notice-fix`. Carry into a future authorized release.
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

Review prepared PR #67 for an authorized merge. Retain the session-expiry fix for
the next authorized application release and verify signed-in navigation then.

Use [delivery](deploy/DELIVERY.md), [workflow](docs/agent-workflow.md) and
`python scripts/release_status.py` when release state matters. Read historical
evidence only for a specific investigation; update facts here instead of appending logs.
