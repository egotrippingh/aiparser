# AIRate current project state

Updated 2026-10-07. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Scan pipeline published through [PR #26](https://github.com/egotrippingh/aiparser/pull/26), merged production source `650e60b53ba36d2249bc83301256336bcf0c1d9e`. [Production CI/deployment](https://github.com/egotrippingh/aiparser/actions/runs/37531443115) passed backup, isolated restore and public readiness checks.
- Published Windows release: **2026.10.6.1**, built from that merged source with the existing agent telemetry configuration. Public metadata and both complete HTTPS artifact hashes verified; **2026.10.2.3** retained as `agent-previous`.
- Durable answer capture overlaps one bounded analysis worker; adaptive provider pauses preserve measured floors and frozen legacy timing. Code passed deterministic checks and independent correctness/risk reviews; [release evidence and limits](docs/scan-pipeline-release.md).

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite, persistent provider profiles; browser scans execute on the client PC.
- `server/`: central FastAPI/PostgreSQL, accounts, managed runs, billing and server analysis.
- `frontend/`: React/Vite; compiled shared interface tracked in `web/`.
- Durable pending answers freeze analysis inputs and payer/check IDs. Successful result/outbox commit removes their raw payload; errors retain it for continuation. No multi-account or VPS work in this change.
- Production delivery retains CI, database backup/isolated restore, pinned SSH host verification, readiness and rollback gates. Optional Sentry error reporting remains in place.

## Open checks

- Live provider throughput and sustained throttling, real-profile power-loss recovery and an upgrade from an older installed version remain unverified. Native isolated install, browser/EXE self-test, same-version reinstall and uninstall/data preservation passed. Synthetic overlap does not establish 0.5 answers/second.
- Full operator-PC HTTPS download timed out; complete downloads/hashes passed from the VPS, and the operator-PC installer range matched the local build.
- Cancellation authorization covers previously reserved checks on the same live assigned device/lease; the server does not prove browser capture time.
- PostgreSQL concurrency, existing-user WebView2/tray/logon behavior and a separate off-VPS database backup remain open.

## Next action

Update the client agent to 2026.10.6.1 and measure an identical real-provider query set before/after. Record capture/analysis times and throttling before reducing measured provider floors or adding multi-account infrastructure.

## References

- [Delivery and rollback](deploy/DELIVERY.md)
- [Capture scope and checks](docs/scan-pipeline-brief.md)
- [Published release checks](docs/scan-pipeline-release.md)
- [Editable language rules](PYTHON_RULES.md)
- [Sentry setup](docs/sentry.md)
