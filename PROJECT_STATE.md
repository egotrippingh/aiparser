# AIRate current project state

Updated 2026-10-02. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Production source: `e7594b2e50c2710bbc412fd83f0c825bfaa2e549` (cost confirmation popovers). Existing Windows agent: **2026.10.1.3**, Camoufox **152.0.4 beta.30**. This task has not deployed or published a new agent.
- New scans cost 120 kopeks per query/service; eligible saved-answer recompute costs up to 80 kopeks per answer. Clarifications/recompute are gated to the configured admin account. Telemetry does not change charging or transaction behavior.

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite, browser profiles and provider adapters; scans execute on the user's PC.
- `server/`: central FastAPI, PostgreSQL, accounts, managed runs, billing and OpenRouter analysis.
- `frontend/`: React/Vite, shared web/agent interface; tracked build in `web/`.
- Production delivery uses GitHub Actions backup/restore verification and readiness checks. Windows artifacts use the existing atomic publication process.

## Prepared Sentry integration

- Optional cloud error reporting covers server/local API, scanner, control synchronization, background scheduler, payment reconciliation, recompute and five React roots. Typed CAPTCHA/auth/confirmed quota/cancellation and expected client HTTP statuses are filtered.
- Only approved exception types, project stack locations, version/environment, fixed tags and scoped internal IDs enter error payloads. A final transport gate drops other envelope types and late SDK metadata; browser IP inference is disabled.
- Account/DSNs are not available. Collection is disabled until configured; cloud ingestion, source-map upload and a published Windows update remain unverified. See [setup and limitations](docs/sentry.md).
- Broad Python checks: 104 passed; after review repairs, 17 telemetry/recompute checks passed. Frontend: 48 tests, lint and build passed. Final Windows portable build and EXE self-test passed. Independent Sol/Astra rechecks found no remaining verified defect. Offline checks use actual SDK envelope serialization. Evidence: ignored `build/qa/sentry-final-20261002-01`, `sentry-risk-regressions-20261002.log`, `sentry-native-final-20261002.log`.
- Docker image execution was not checked locally because its daemon is unavailable. Live cloud ingestion, private source maps, installed-agent upgrade and production activation remain unverified.

## Other open checks

- Existing-user native upgrade, WebView2/tray/logon behavior, power-loss recovery, real provider scan with clarification, paid recompute and PostgreSQL concurrency remain unverified by this task.
- Google completion uses a quiet-time heuristic; nonempty Google source preservation and sustained provider limits need live validation.
- An off-VPS database backup destination is not confirmed. Windows release automation is being worked on separately; this branch does not include that work.

## Next action

Review the Sentry PR into `production`. Create a Sentry organization and Python server, Python agent and React projects; configure their public DSNs. Install the Compose change via the existing operator process, deploy the reviewed release and verify one deliberate test error per component. Bump the agent version before publishing its next release.

## References

- [Delivery and rollback](deploy/DELIVERY.md)
- [Sentry setup](docs/sentry.md), [task brief](docs/sentry-brief.md)
- [Previous project state and release evidence](docs/history/project-state-before-sentry-2026-10-02.md)
