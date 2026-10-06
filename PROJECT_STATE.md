# AIRate current project state

Updated 2026-10-06. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Production API reports `fdacff6d2f2a7da1aa02e7e737696e4705bd3750` through public `/api/v1/ready`.
- Published Windows release: **2026.10.2.3**, confirmed through public download metadata. This task has not built or published a replacement installer.
- Prepared feature branch `codex/scan-pipeline-timing`, agent version **2026.10.6.1**: durable answer capture overlaps one bounded analysis worker; adaptive provider pauses preserve measured floors and frozen legacy timing.
- Deterministic checks and independent reviews are recorded in [capture scope/evidence](docs/scan-pipeline-brief.md). Delivery remains a feature PR; prepared code is not a deployed release.

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite, persistent provider profiles; browser scans execute on the client PC.
- `server/`: central FastAPI/PostgreSQL, accounts, managed runs, billing and server analysis.
- `frontend/`: React/Vite; compiled shared interface tracked in `web/`.
- Durable pending answers freeze analysis inputs and payer/check IDs. Successful result/outbox commit removes their raw payload; errors retain it for continuation. No multi-account or VPS work in this change.
- Production delivery retains CI, database backup/isolated restore, pinned SSH host verification, readiness and rollback gates. Optional Sentry error reporting remains in place.

## Open checks

- Live provider throughput and sustained throttling, real-profile power-loss recovery and installed-EXE upgrade are unverified by this change. Synthetic overlap does not establish 0.5 answers/second.
- Cancellation authorization covers previously reserved checks on the same live assigned device/lease; the server does not prove browser capture time.
- PostgreSQL concurrency, existing-user WebView2/tray/logon behavior and a separate off-VPS database backup remain open.

## Next action

Review and merge the feature PR into `production` after CI passes, then use the existing Windows build/publication gates for 2026.10.6.1 and measure a real scan. Current users remain on published 2026.10.2.3 until a replacement is verified.

## References

- [Delivery and rollback](deploy/DELIVERY.md)
- [Capture scope and checks](docs/scan-pipeline-brief.md)
- [Editable language rules](PYTHON_RULES.md)
- [Sentry setup](docs/sentry.md)
