# AIRate current project state

Updated 2026-10-07. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Provider hotfix published through [PR #30](https://github.com/egotrippingh/aiparser/pull/30), production source `091f1908e71bfa5300a17884988677446097031f`; [CI/deploy](https://github.com/egotrippingh/aiparser/actions/runs/37623664538) and public readiness passed. Current Windows release: **2026.10.7.2**. Final EXE/browser, isolated install/reinstall/uninstall, 3662 file comparisons and data-preservation checks passed. Complete public HTTPS hashes verified from the VPS; operator-PC installer prefix matched. **2026.10.7.1** retained as previous release. [Provider scope, hashes and limits](docs/provider-e2e-brief.md).
- Throughput follow-up published through [PR #28](https://github.com/egotrippingh/aiparser/pull/28), production source `fba1f8466457666f04ded8cc180ae3a25cf64276`. [Production CI/deployment](https://github.com/egotrippingh/aiparser/actions/runs/37602006061) passed backup, isolated restore and public readiness checks.
- Previous Windows release: **2026.10.7.1**, built from the identical reviewed/merged source tree with existing telemetry configuration. Isolated EXE/browser/install/reinstall/uninstall checks and 1819 file comparisons passed. Public metadata and complete HTTPS artifact hashes passed from the VPS; operator-PC installer prefix matched. **2026.10.6.1** retained as `agent-previous`.
- Durable answer capture overlaps one bounded analyzer. Screenshot uploads run separately, HTTP clients reuse connections, planning omits screenshot BLOBs, and phase timings identify waits. Adaptive provider floors and legacy timing remain intact. Saved retry/abandonment and account ownership passed independent correctness/risk reviews and actual local-handler checks; [release evidence and limits](docs/scan-throughput-release.md).
- Two analyzers remain a local developer experiment; direct fill, scroll skipping and Google DOM readiness remain explicit QA flags. Full live image completeness was not qualified, so production Google/screenshot defaults were not changed. No sustained 0.5 answers/second claim.

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite, persistent provider profiles; browser scans execute on the client PC.
- `server/`: central FastAPI/PostgreSQL, accounts, managed runs, billing and server analysis.
- `frontend/`: React/Vite; compiled shared interface tracked in `web/`.
- Durable pending answers freeze analysis inputs and payer/check IDs. Successful result/outbox commit removes their raw payload; errors retain it for continuation. Abandonment retains evidence and an uploadable error, releases/settles once, prevents resurrection and durably reports managed termination. No multi-account or VPS work in this change.
- Production delivery retains CI, database backup/isolated restore, pinned SSH host verification, readiness and rollback gates. Optional Sentry error reporting remains in place.

## Open checks

- Live provider throughput and sustained throttling, real-profile power-loss recovery and an upgrade from an older installed version remain unverified. Native isolated install, browser/EXE self-test, same-version reinstall and uninstall/data preservation passed. Synthetic two-analyzer median improved ~24% in the final local run; this does not establish real-provider throughput.
- Complete operator-PC HTTPS artifact downloads are not qualified; complete downloads/hashes passed from the VPS, and the operator-PC installer range matched the local build.
- Cancellation authorization covers previously reserved checks on the same live assigned device/lease; the server does not prove browser capture time.
- PostgreSQL concurrency, existing-user WebView2/tray/logon behavior and a separate off-VPS database backup remain open.

## Next action

Update WEB-PM ЕГОР to 2026.10.7.2 and measure an identical real-provider query set before/after with valid sessions. Record capture/queue/analysis/upload times and throttling before promoting experiments or adding multi-account infrastructure. After using abandonment, do not downgrade its local database to an older agent; recovery requires a forward-versioned fix preserving abandoned-state filters and terminal markers.

## References

- [Delivery and rollback](deploy/DELIVERY.md)
- [Capture scope and checks](docs/scan-pipeline-brief.md)
- [Published release checks](docs/scan-pipeline-release.md)
- [Throughput follow-up checks and rollback limits](docs/scan-throughput-release.md)
- [Editable language rules](PYTHON_RULES.md)
- [Sentry setup](docs/sentry.md)

## Provider E2E status (2026-10-07)

Forward hotfix **2026.10.7.2** is published. Supplied WEB-PM logs confirm 28 four-minute ChatGPT completion waits. Verified guest DOM supports the new completion flag, composer and answer selectors; the latest message owns completion. Alice readiness accepts every visible authenticated marker, including the verified hybrid-sidebar account name. Fresh browser work is bounded to 900 seconds, fails one query on timeout and retains the service tail for continuation; stop preserves an underway capture and saved analysis work. Device polls expose version and per-service phase without query text.

Final focused checks: **49 passed**; server suite: **74 passed**. Real headless local Google/Alice pipeline: **6/6 answers in 89.08 seconds**, six valid images, no paid analysis. Independent correctness/risk reviews found no blockers; final Windows installation and public artifact checks passed. Broad single-process agent collection remains failing; pristine baseline reproduced its first three API smoke failures.

Remote authenticated ChatGPT, exact Google hung substep, broad Alice readiness across profiles/modes, screenshot completeness and Google citation extraction remain unqualified. WEB-PM must update and rerun a bounded query set before remote behavior can be qualified; [scope/evidence](docs/provider-e2e-brief.md).
