# AIRate current project state

## Promo codes and CSV import help (2026-10-14, local)

Branch codex/promo-codes adds admin-created per-service free scans (including zero),
redemption at email registration and account/top-up, once per code/account.
Different codes accumulate; saved-answer recompute stays paid. Credits are frozen
at cloud-run creation and refunded once when unused, with wallet locking and a
fresh Check read preventing concurrent double refunds. CSV import now explains
UTF-8, columns/delimiters and escaping in an accessible popover with a template.
Final server277 passed with disposable PostgreSQL; agent billing/scan52 and
frontend85/lint/build passed. Desktop1280px/mobile390px browser success/error,
registration, quote and CSV help/import checks passed; no final console errors.
Sol/Astra reviews completed; the confirmed refund race was reproduced then fixed.
Hover is configured but pointer-only hover and OS template download completion
were not verified. No live paid provider/payment checks or production deployment.
Additive migration20261014_promo_codes is required at publication through normal
delivery gates. Evidence: C:/codex-tmp/airate-promos-20261014/;
see [promo-codes.md](docs/tasks/promo-codes.md).

## Scrapeless webhook and timeout recovery (2026-10-13, deployed)

Branch codex/scrapeless-webhook adds attempt-scoped notifications, authenticated
GET evidence recovery and automatic retry after15min without a confirmed handle.
One AIRate Check/settlement is preserved; old results remain unchanged. Unknown
confirmation is capped at3 total submissions, then isolated; other slots/users run.
Known pending IDs retain one slot and are polled without duplicate submission.
Full server262, focused19 and shared67 passed with disposable PostgreSQL.
Sol/Astra reviewed final risky changes without blockers. Caddy URI redaction
passed an actual502 check; production Caddy2.11.4 validated/reloaded with backup.
PR #57 merged after exact-head CI38391368321 passed on3a633685.
Production CI38391886578 passed on50f18ee979d980f450c9f458f4007bc1f72e626d;
normal HTTPS readiness confirms the exact release and pricing120.
The live geosoft-dent uncertain task recovered automatically: attempt2 completed,
answer saved, one Check settled. ChatGPT303/303; Yandex278/303 still processing.
Invalid public callback returned404. No scan records were edited manually.
See [scrapeless-webhook.md](docs/tasks/scrapeless-webhook.md).

## Provider queue isolation (2026-10-13, deployed)

Branch codex/provider-isolation removes account-wide pauses for individual unknown
Scrapeless sends and XML transient failures, while preserving occupied slots,
global auth/quota guards and ambiguous-POST no-resend. XML network exhaustion is
classified as a retryable query failure. No schema or frontend change.
Five regressions failed before the fix; focused provider/XML96 and shared67 pass
with disposable PostgreSQL. Final full server243 passed; Sol/Astra reviews passed.
Full-capacity regression covers slot reuse in the same tick. PR56 merged after
exact-head CI38384826583 passed. Production CI38385385962 passed;
HTTPS readiness confirms67575132d4f4d3b0852fc9c62bd7e5fdbb2f8aab and pricing120.
Live geosoft-dent: ChatGPT121 ->301 of303, Yandex186 ->203 of303 after activation.
One pre-existing uncertain POST is retained without resend; one expired handle
and the remaining Yandex tail still require normal recovery/provider responses.
See [provider-isolation.md](docs/tasks/provider-isolation.md).

## Automatic collection recovery and report filters (2026-10-13)

PR #55 recovers new complete-policy empty/failed/expired tasks automatically;
an expired handle is rechecked before another paid submission. Deferred tasks
leave free provider slots usable, with bounded admission and durable shared cooldowns.
Original completed history and one wallet settlement per Check are preserved.
Reports expose independent external-source/product-card switches; own-domain mode
uses safe HTTP(S) sources consistently across charts, totals, tables and XLSX.
Final full server: 229 passed with disposable PostgreSQL; frontend84/lint/build,
XMLRiver27 and desktop/mobile keyboard QA passed. Sol/Astra reviews completed.
PR CI 38372134424 and production CI 38372769409 succeeded. No schema change.
Live geosoft-dent scan advanced from 576 to706 of1212 after activation.
Evidence: C:/codex-tmp/airate-recheck-qa/; [collection-recheck.md](docs/tasks/collection-recheck.md).

## Monthly calendar completion (2026-10-13)

Branch codex/schedule-calendar starts from production b165c429dc94b3de312072ec8cfa60f334723cc8
and preserves PRs #49–53. Server last_day support and actual-scan chart dates are
already published; the remaining UI now offers 1–28 and the last-day flag, including
last-day-only schedules, explicit legacy 29–31 removal and complete schedule labels.
84 frontend checks, lint/build, 8 schedule regressions and desktop/390px disposable
browser checks passed; independent Sol review found no blockers. No schema change.
Evidence: C:/codex-tmp/airate-schedule-calendar-20261013/; task
[scan-calendar-days.md](docs/tasks/scan-calendar-days.md).
PR #54 is merged into production 99d7fb34584eb9b12dab1378d7b73960fe4a86a5.
PR CI 38357093941 passed; production CI 38357731853 passed Tests and build and
Upload and activate verified release, then failed Verify public release.
After email confirmation, Radix RDAP no longer reports client hold and Google DNS
resolves the domain to 45.146.90.88. Normal HTTPS public verification passed on
2026-10-13: exact release SHA, pricing, 12 matching assets and anonymous private
routes returning 401. The original failed CI run remains historical; no gate was bypassed.

## Current release

Production is `50f18ee979d980f450c9f458f4007bc1f72e626d` from PR #57.
Normal HTTPS verification confirms the exact SHA and pricing120;
an invalid callback returns404. Production CI and readiness passed.
Previous records were verified unchanged during the PR #51/#52 migration.
Historical release evidence is in
[project-state-history-2026-10-12.md](docs/project-state-history-2026-10-12.md).

## Delivered change

PR #51 delivers public news, admin-only publishing, provider pause
admission controls and sparse actual-scan chart dates. Migration
`20261012_news_provider_pauses` is live and additive. Application rollback requires
`airate-web:news-rollback-62536ba7389f`, verified against the restored migrated DB;
the old application image cannot start against this schema.
See [news-service-pauses.md](docs/tasks/news-service-pauses.md).

## Architecture

`server/` owns accounts, runs, billing and cloud collection; `frontend/` builds the
tracked `web/` interface. Production delivery retains CI, backup/restore, migration
checks, readiness and rollback gates.

## Open checks and next action

Geosoft-dent remains in progress; complete-run live verification is still pending.
An automatic provider retry can spend provider balance again; the client Check
settles once. No live new scan/payment was initiated for QA. The disposable
PostgreSQL instance and report QA server started for these checks are stopped.
## Delivered answer display

PR #52 renders reference citations, removes synthetic answer tiles
and suppresses duplicate source footers. Its 83 frontend tests, lint/build and
desktop/mobile fixture checks passed. Both changes are deployed in the same release.
See [answer-display.md](docs/tasks/answer-display.md).
