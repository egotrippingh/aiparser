# AIRate current project state

Updated 2026-10-02. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Production source: `556dc031e17a384ac4d6914b0a187e0af45c7644`, merged Google/report PR [#23](https://github.com/egotrippingh/aiparser/pull/23). Production CI [37014201642](https://github.com/egotrippingh/aiparser/actions/runs/37014201642), actual backup/isolated-restore logs and public readiness passed.
- Windows **2026.10.2.2** is published with its cloud DSN, built from the same merged source. Isolated installation, bundled-browser self-test, same-version reinstall and data-preserving uninstall passed. Complete public installer/ZIP sizes and SHA-256 match the tested build via HTTPS from the VPS. Previous **2026.10.2.1** remains for rollback. Camoufox **152.0.4 beta.30**. Evidence: ignored `build/qa/google-fix-release-evidence.json`.
- Google consent and dated-report checks passed: Google 14, overview 23, exports 7, server reports 5, frontend 50; scan self-check, lint and build passed. Final Sol/Astra reviews found no remaining actionable findings. Isolated UI proves GPT-only October 2 has unchecked cells and zero result buttons while September 26 login errors remain historical. See [scope and evidence](docs/google-consent-report-brief.md).
- New scans cost 120 kopeks per query/service; eligible saved-answer recompute costs up to 80 kopeks per answer. Clarifications/recompute are gated to the configured admin account. Telemetry does not change charging or transaction behavior.

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite, browser profiles and provider adapters; scans execute on the user's PC.
- `server/`: central FastAPI, PostgreSQL, accounts, managed runs, billing and OpenRouter analysis.
- `frontend/`: React/Vite, shared web/agent interface; tracked build in `web/`.
- Production delivery uses GitHub Actions backup/restore verification and readiness checks. Windows artifacts use the existing atomic publication process.

## Deployed Sentry integration

- Optional cloud error reporting covers server/local API, scanner, control synchronization, background scheduler, payment reconciliation, recompute and five React roots. Typed CAPTCHA/auth/confirmed quota/cancellation and expected client HTTP statuses are filtered.
- Only approved exception types, project stack locations, version/environment, fixed tags and scoped internal IDs enter error payloads. A final transport gate drops other envelope types and late SDK metadata; browser IP inference is disabled.
- Organization `airate` and projects `airate-server`, `airate-agent`, `airate-browser` are configured for errors only. Production Compose and DSNs are installed; unrelated environment values were preserved. Root-only rollback copy: `/root/airate-sentry-config-20261002T071102Z`. See [setup and limitations](docs/sentry.md).
- Broad Python checks: 104 passed; after review repairs, 17 telemetry/recompute checks passed. Frontend: 48 tests, lint and build passed. Final Windows portable build and EXE self-test passed. Independent Sol/Astra rechecks found no remaining verified defect. Offline checks use actual SDK envelope serialization. Evidence: ignored `build/qa/sentry-final-20261002-01`, `sentry-risk-regressions-20261002.log`, `sentry-native-final-20261002.log`.
- GitHub [run 36977330237](https://github.com/egotrippingh/aiparser/actions/runs/36977330237) passed tests, production deployment, database backup and isolated restore. Public readiness reports the exact production SHA. Synthetic server, runtime-configured browser and frozen-agent-code events appeared in Sentry with environment `production`; ingestion returned HTTP 200. Evidence: ignored `build/qa/sentry-production-deploy.log`, `sentry-live-check.json`, `sentry-frozen-cloud-check.json`, `sentry-production-projects.jpg`.
- Windows installer checks passed: 3,566 installed files match the source bundle, installed EXE self-test, same-version reinstall and uninstall preserving isolated data and legacy portable data. Installed runtime reports version **2026.10.2.1**, environment `production` and the expected agent DSN. Evidence: ignored `build/qa/sentry-installed-lifecycle.log`, `sentry-installed-runtime.json`. This does not establish an upgrade from a real older installation or actual installed-EXE error ingestion. Private browser source maps remain unconfigured.
- Publication switched atomically to **2026.10.2.1**, retaining **2026.10.1.3** for rollback. Public API metadata and complete installer/ZIP sizes and SHA-256 match the tested build. Full downloads were checked through public HTTPS URLs from the VPS; the operator-PC attempt timed out. Evidence: ignored `build/qa/sentry-public-artifacts.json`, `sentry-agent-resume-fixed.log`.

## Other open checks

- Existing-user native upgrade, WebView2/tray/logon behavior, power-loss recovery, real provider scan with clarification, paid recompute and PostgreSQL concurrency remain unverified by this task.
- Google completion uses a quiet-time heuristic; nonempty Google source preservation and sustained provider limits need live validation.
- An off-VPS database backup destination is not confirmed. Windows release automation is being worked on separately; this branch does not include that work.

## Next action

Existing users should update to **2026.10.2.2** after their active scan finishes. Confirm actual Google consent dismissal on WEB-PM ЕГОР; real older-installation upgrade and live provider scans remain unverified by this delivery.

## References

- [Delivery and rollback](deploy/DELIVERY.md)
- [Sentry setup](docs/sentry.md), [task brief](docs/sentry-brief.md)
- [Previous project state and release evidence](docs/history/project-state-before-sentry-2026-10-02.md)
