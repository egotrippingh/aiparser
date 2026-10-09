# AIRate current project state

## XMLRiver server implementation awaiting controlled activation (2026-10-09)

The user selected server collection and text analysis for `google_aio` and
`yandex_neuro`, without a Windows agent, browser or screenshots. Other providers
keep their agent path. Branch `codex/xmlriver-ai`, source `9956c06`, implements
durable server captures, frozen geography/identity, bounded collection/model
retries, once-only settlement and mixed cloud-then-agent runs. Cloud-only launch
and schedules require no computer. Existing runs retain their original path.

The result dialog renders safe structured XMLRiver evidence, red brand/alias and
brand-domain accents, source links and an accessible carousel for actual returned
product photos. An offline replay of the saved Yandex example contains five
products and five photo URLs; the saved Google example contains no product cards.
This is response-specific evidence, not a guarantee for every query.

Checks on the integrated implementation: 76 shared parser/rules/LLM tests,
58 pipeline/durable/billing/storage checks, 46 readiness/watchdog checks and
56 frontend tests passed; frontend lint has warnings and no errors, build passed.
Disposable desktop/390px browser checks passed for evidence dialogs, highlights,
carousel keyboard controls, image failure, detail API failure and cloud launch
without a computer; no JavaScript console errors or page overflow. Sol final
correctness/risk re-review on `9956c06` found no P1/P2. Its final root server
suite passed 112 tests. A reproduced synchronous DB lock wait now executes
outside the main asyncio loop; regressions cover responsiveness and finishing
the current tick before AI-client shutdown. Exact-head CI is pending.
Evidence remains outside Git under
`~/.codex/tmp/xmlriver-html-preview-20261009/`.

Production is still `656099acfbb41d29c30261620023143e443aad1c`. PR #35 remains
open at the earlier main head; do not merge it until the new implementation is
reviewed and the server configuration/schema are ready. The authorized activation
requires the new `20261009_server_captures` migration, Compose installation and
XMLRiver secrets through administrator access. Password SSH is disabled on this
VPS; administrator access was established through the authenticated Aeza console
and an explicitly authorized temporary key restricted by source IP/expiry.
The SSH host key was verified against the console fingerprint. Existing backup
and isolated restore passed on the live PostgreSQL server before migration.
Follow [the controlled release procedure](docs/xmlriver-cloud-release.md),
including backup, isolated PostgreSQL restore/migration validation and exact-SHA
readiness. No production migration, new deployment, live model/payment test or
new Windows installer publication has occurred. Docker import validation is a
new CI gate; Docker is unavailable on the local PC.

### Earlier agent implementation and release hold

Branch `codex/xmlriver-ai` adds opt-in XMLRiver capture for Google AI Overview
and the existing Yandex Neuro SERP identity. Feature [PR #34](https://github.com/egotrippingh/aiparser/pull/34)
was merged to `main` at `66c9086145d270360a0faa8954618efb18b429e6` after
CI success on source `9f9d31b11d260e10e013a0fe7ab8e5c39c58fa47`.
Production [PR #35](https://github.com/egotrippingh/aiparser/pull/35) is open,
not merged or deployed; Windows `2026.10.9.1` is prepared but unpublished.
Provider/geography are frozen for resume; saved
captures continue through the existing analyzer and settlement path. Google
legacy scans remain browser-backed. Setup and the local screenshot provenance
are documented in [README.md](README.md). Final checks passed: 322 Python tests,
51 frontend tests, lint/build, benchmark self-check and diff check. Two Linux-only
publication tests were skipped on Windows. Sol/Astra re-review found no remaining
blockers. Fresh-context UI smoke passed at desktop/narrow widths, including
keyboard selection, save errors and API readiness. Two final live XMLRiver calls
returned Google/Yandex AI captures with valid images and no render requests or
credential logs. This verifies capture, not live model/payment or load behavior.
Local evidence: `~/.codex/tmp/xmlriver-ai-20261009/checks-100338/report.json`.

Retry follow-up on the same branch: malformed/partial XML, invalid base64/HTML
and empty extracted AI main text are recollected automatically before publishing
an error. All transient failures share three HTTP attempts with 1/2-second waits;
stop/cancel prevents new requests, saved answers are not recollected. Exhausted
attempts remain recoverable errors; auth/quota and valid absence do not retry.
Scoped checks: 62 XMLRiver/pipeline tests, 46 readiness/watchdog tests and 52
pipeline/durable/billing/storage tests passed (133 distinct tests), including
offline browser renders. Benchmark self-check and diff check passed. Independent
Sol review found no blockers. This follow-up used fake API responses only; no
live XMLRiver, model, payment or deployment check.

Before production merge the user changed scope: use XMLRiver text for analysis
and show its HTML instead of screenshots. Deployment is held pending this
change and the server-versus-agent execution decision. Current code still uses
agent/local rendering/screenshots; do not describe it as agent-free. User asked
to inspect saved real Google/Yandex HTML first. Safe previews (same vacuum query,
no new provider calls) are outside Git at
`~/.codex/tmp/xmlriver-html-preview-20261009/{google,yandex}.html`, served on
`http://127.0.0.1:8874/`; both pages were opened in the app browser. Scripts and
external resources are removed; display styling is local, not native SERP styling.

Updated 2026-10-08. Repository: `egotrippingh/aiparser`; development branch: `main`;
deployment branch: `production`.

## Current release

- Project feedback and admin scan review from [PR #32](https://github.com/egotrippingh/aiparser/pull/32) published 2026-10-08 through [production PR #33](https://github.com/egotrippingh/aiparser/pull/33), source `656099acfbb41d29c30261620023143e443aad1c`. [CI/deploy](https://github.com/egotrippingh/aiparser/actions/runs/37759036779) passed; logs confirm verified image upload, isolated database restore, saved backup and activation. Public readiness matches that SHA, pricing remains 120 kopeks, cabinet serves the new feedback/admin bundle, and unauthenticated admin review returns 401. No schema migration or new Windows agent release. [Evidence and limits](docs/scan-feedback.md).
- Provider hotfix published through [PR #30](https://github.com/egotrippingh/aiparser/pull/30), production source `091f1908e71bfa5300a17884988677446097031f`; [CI/deploy](https://github.com/egotrippingh/aiparser/actions/runs/37623664538) and public readiness passed. Current Windows release: **2026.10.7.2**. Final EXE/browser, isolated install/reinstall/uninstall, 3662 file comparisons and data-preservation checks passed. Complete public HTTPS hashes verified from the VPS; operator-PC installer prefix matched. **2026.10.7.1** retained as previous release. [Provider scope, hashes and limits](docs/provider-e2e-brief.md).
- Throughput follow-up published through [PR #28](https://github.com/egotrippingh/aiparser/pull/28), production source `fba1f8466457666f04ded8cc180ae3a25cf64276`. [Production CI/deployment](https://github.com/egotrippingh/aiparser/actions/runs/37602006061) passed backup, isolated restore and public readiness checks.
- Previous Windows release: **2026.10.7.1**, built from the identical reviewed/merged source tree with existing telemetry configuration. Isolated EXE/browser/install/reinstall/uninstall checks and 1819 file comparisons passed. Public metadata and complete HTTPS artifact hashes passed from the VPS; operator-PC installer prefix matched. **2026.10.6.1** was retained as `agent-previous` at that release.
- Durable answer capture overlaps one bounded analyzer. Screenshot uploads run separately, HTTP clients reuse connections, planning omits screenshot BLOBs, and phase timings identify waits. Adaptive provider floors and legacy timing remain intact. Saved retry/abandonment and account ownership passed independent correctness/risk reviews and actual local-handler checks; [release evidence and limits](docs/scan-throughput-release.md).
- Two analyzers remain a local developer experiment; direct fill, scroll skipping and Google DOM readiness remain explicit QA flags. Full live image completeness was not qualified, so production Google/screenshot defaults were not changed. No sustained 0.5 answers/second claim.

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite, persistent provider profiles; browser scans execute on the client PC.
- `server/`: central FastAPI/PostgreSQL, accounts, managed runs, billing and server analysis.
- `frontend/`: React/Vite; compiled shared interface tracked in `web/`.
- Durable pending answers freeze analysis inputs and payer/check IDs. Successful result/outbox commit removes their raw payload; errors retain it for continuation. Abandonment retains evidence and an uploadable error, releases/settles once, prevents resurrection and durably reports managed termination. No multi-account or VPS work in this change.
- Production delivery retains CI, database backup/isolated restore, pinned SSH host verification, readiness and rollback gates. Optional Sentry error reporting remains in place.

## Open checks

- Feedback/admin review is deployed; live model accuracy, authenticated production feedback/admin flows and the original Neighbours Expert verdict cause remain unverified. See [scope and checks](docs/scan-feedback.md).

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
