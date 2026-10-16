# AIRate state snapshot before workflow cleanup — 2026-10-16

Historical evidence only. Superseded next-action statements below are retained as
recorded; use [PROJECT_STATE.md](../PROJECT_STATE.md) for current facts.

Updated 2026-10-16. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Pushed to development `main`, not deployed 2026-10-16: `619ac9c9038d4a6e69ea3b613f7d834bf5f65bfd` fixes duplicate invalid-session notices via one expiry owner. 81 frontend tests/lint/build and disposable browser expiry check passed; focused review closed. Isolated source: C:/Users/ego/.codex/worktrees/session-notice/aiparser. Production remains `28972c5`; carry this patch into a future authorized release.

- Published and verified 2026-10-16: [PR #66](https://github.com/egotrippingh/aiparser/pull/66), release `28972c5157e5c1fd0123703d07db5d993f8a93f7`, schema unchanged. Desktop UI/downloads retired; icon-only rail with custom tooltips, header All Projects button separate from searchable chooser. 336 server and 97 frontend CI tests passed; correctness/risk reviews closed. Production run 38879609015 passed, isolated backup restore and exact readiness/10 asset hashes/5 retired routes verified. Local signed-in keyboard/tooltip/search/mobile smoke and live guest registration/landing smoke passed; signed-in live smoke unavailable without an active session. Evidence: build/retire-agent-20261016/.

- Published and verified 2026-10-16: [PR #65](https://github.com/egotrippingh/aiparser/pull/65), release `077590eb88fb397f3bcd4d0088ab3b07ddd18fa0`, schema unchanged. Shared guest/authenticated header, searchable projects moved from sidebar, balance/top-up and account menu. Correctness/auth-deploy risk reviews closed; 335 server and 95 frontend CI tests passed. Production run 38875108243 passed, backup restored in isolation, exact readiness/assets and signed-in live project search/navigation/account menu verified. Evidence: build/header-release-20261016/. Next: observe normal guest/account use; no further release work pending.

- External configuration verified 2026-10-15: Yandex OAuth service icon replaced with the current orange AIRate mark. Padded SVG avoids circular cropping; saved icon confirmed after reopening settings. OAuth permissions, redirect URIs and credentials unchanged.

- Published and verified 2026-10-15: [PR #64](https://github.com/egotrippingh/aiparser/pull/64), release `96ac2018d87a6ff9fa7c6b18b01f1daee993a61a`, schema unchanged. Shared Yandex OAuth URL requests confirmation/account choice with `force_confirm=yes` for login and linking. Full CI, backup restore, exact live readiness and live redirect parameters passed.
- Design retained from [PR #63](https://github.com/egotrippingh/aiparser/pull/63), release `5c8322a691af237947f2fa420c75b1bed4d32a02`, schema unchanged (`20261015_email_registration`). Approved login/registration and balance top-up design, one Yandex entry, payment method icons and generic commission notice. Full CI/deploy, backup restore, exact live assets/readiness and public login browser check passed. Local production and working branch are synchronized.
- PR #62 metric policy remains deployed: absent AI blocks count as checks without mentions. Read-only production evidence: vidnal.ru Yandex 10/29 = 34.5%; all services 17/58 = 29.3%.
- PR #61 email-code registration and Yandex signup remain deployed; no schema or authentication change in PR #62.
- PR #60 balance top-up notifications remain active through SMTP.BZ; real Coinso credits atomically queue HTML/plain-text email.
- PR #59 password completion for Yandex registrations, password settings/recovery and promo availability/limits/expiry remain deployed. Password recovery is now available through the verified SMTP configuration.
- Manual scan and saved-answer recompute use anchored cost popovers with a fresh server quote, cancellation and stale-quote protection. This frontend release does not change billing API or agent version.
- New scans cost **120 kopeks per query and service** and automatically use fast timings. Saved-answer recompute costs up to **80 kopeks per eligible answer**; failed analysis is skipped without charge. Saving a brand clarification is free and affects future scans. Clarifications/recompute remain gated to the exact `ivoryya` admin account.
- Captured answers preserve formatting, tables and available source links. Errors show reasons and guidance. Ordinary failed queries do not retry automatically; starting a new project scan checks all its queries. Selective retry is not implemented.

## Architecture

- New checks run on the server for all five services; the website configures projects and displays reports. Desktop distribution/UI are retired in PR #66. `app/detect` remains shared server detection code; remaining desktop/runtime code and device protocols support historical data compatibility.
- `server/`: central API, accounts, PostgreSQL, managed runs and billing. Managed checks use control-plane query UUIDs; local integer IDs remain for unmanaged runs. Pending uploads use the agent outbox.
- `frontend/`: React/Vite landing, web cabinet and legal pages; built site assets live in `web/`.
- Production: `https://airate.tech`; screenshots in Yandex S3; semantic analysis via OpenRouter. GitHub Actions deploys `production` with backup/restore verification, serialized activation and readiness checks. No Windows artifacts are built or published by website delivery.

## Open checks and limitations

- A real provider scan with a clarification, historical S3 screenshot recovery, paid saved-answer recompute and a live PostgreSQL upload/recompute race remain unverified.
- An off-VPS database backup destination is not confirmed; the delivery guide currently records VPS-local backups.

## Next action

PR #66 is published and verified. Next: observe normal signed-in use of the icon rail and header navigation. Older Windows build/upgrade checks are retired, not open website-release gates. See [retirement scope](../docs/desktop-retirement.md).

Yandex account selection is published and verified: production run 38749602674 succeeded, backup restored, exact live release and OAuth redirect parameters checked. All 13 focused Yandex tests, 335 server and 92 frontend CI tests passed; independent correctness/auth-risk reviews closed. Local production and working branch are synchronized. Real signed-in multi-account provider UI remains unverified. Next: observe the first real paid top-up notification.

Corporate mail: support/hello/noreply@airate.tech remain at REG.RU. SMTP.BZ is approved and enabled in production via connect.smtp.bz:2525 STARTTLS; final-container authentication returned 235. The approved demo HTML test to egorjojori@gmail.com was accepted and the user confirmed Inbox delivery. Existing REG.RU MX/DKIM were preserved; merged SPF, SMTP.BZ DKIM and stats CNAME were verified during setup. Tracking is disabled; transactional mode is enabled. Secrets remain in the private local SMTP file and production .env (0600). Earlier Aéza/REG.RU support ticket status was not rechecked.

Deployed: six-digit email code, ten-minute expiry, five wrong attempts, resend cooldown and serialized PostgreSQL email/IP sending limits. No account/wallet/session exists before proof; promo/connect errors roll back the complete registration. The cabinet restores pending confirmation after reload and explicitly offers Yandex registration. The approved HTML/plain-text template and embedded logo are connected to SMTP.BZ. Current password recovery still sends plain text. See [registration operation](../docs/registration-email.md).

PR #60 is merged and deployed. Reviewed operator rehearsal and live migration preserved all prior rows/columns in 30 tables; the new queue was empty before workers started. A fresh backup was restored/verified before activation. Compatible fallback source 9b32129, image and checksum-verified archive are retained in /opt/airate/releases/mail-20261015. Final CI run 38685256024 attempt 2 passed; production SMTP/auth/recovery/readiness checks passed with no missing/invalid post-cutover notification rows. Detailed evidence is in the PR and private operator folder; local summary: build/mail-release-20261015/release-evidence.json.

Next: observe the first real paid top-up notification. No real payment or artificial balance credit was performed for this release. SMTP-uncertain/sending outcomes require provider-log inspection per docs/topup-emails.md; old paid orders are not backfilled.

The previous cloud scan completed all 300 provider tasks and reached done at 20:59 MSK on 2026-10-14 after PR #59 deployment. Older Windows notes in this checkout predate current production; consult the production branch for current runtime details.

## Checks and references

Read [AGENTS.md](../AGENTS.md) for verification commands and review rules. Historical test counts describe earlier revisions; run checks appropriate to the current change.

- [Delivery, backups and rollback](../deploy/DELIVERY.md)
- [Updater](../docs/updater.md), [session preservation](../docs/session-preservation.md)
- [Managed check identifiers](../docs/managed-check-identifiers.md), [error diagnostics](../docs/report-response-diagnostics.md)
- [Scan timing and benchmark](../docs/scan-delays.md), [answer capture/rendering](../docs/answer-readability.md)
- [Coinso integration](../docs/coinso.md)
- Earlier local history was recorded in `docs/project-state-history-2026-10-01.md` (not included in this snapshot).


Published and verified: absence of an AI block (`skipped`) is a check without a mention; technical errors stay outside the denominator. Historical cloud reports recalculate on read without data writes, billing changes or paid rescans. PR #62 regression checks: 32 targeted server tests, 89 frontend tests, full CI and independent review. Next: observe real top-up notifications and continue the pending Aéza SMTP follow-up. [Metric policy and release](https://github.com/egotrippingh/aiparser/pull/62).
