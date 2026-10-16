# AIRate current project state

Updated 2026-10-16. Repository: `egotrippingh/aiparser`; deployment branch: `production`.

## Current release

- Prepared 2026-10-16: session-expiry fix ported from `main` commit `619ac9c` onto production `28972c5`. One login notice replaces concurrent 401 banners; password rejection/rotation and stale responses are covered. 103 frontend tests, lint/build, disposable browser expiry check (one notice, no remaining dashboard) and focused independent auth review passed. Release remains pending CI/deployment.
- Published and verified 2026-10-15: PR #61, release `8f6540fe444c18758b58647c385f74342e653bdd`, schema `20261015_email_registration`. Password registration requires an email code; Yandex registration/login remains available. CI attempt 2, public readiness/assets, SMTP TLS/auth and registration guards passed. [Release evidence](https://github.com/egotrippingh/aiparser/pull/61).
- PR #60 balance top-up notifications remain active through SMTP.BZ; real Coinso credits atomically queue HTML/plain-text email.
- PR #59 password completion for Yandex registrations, password settings/recovery and promo availability/limits/expiry remain deployed. Password recovery is now available through the verified SMTP configuration.
- Manual scan and saved-answer recompute use anchored cost popovers with a fresh server quote, cancellation and stale-quote protection. This frontend release does not change billing API or agent version.
- New scans cost **120 kopeks per query and service** and automatically use fast timings. Saved-answer recompute costs up to **80 kopeks per eligible answer**; failed analysis is skipped without charge. Saving a brand clarification is free and affects future scans. Clarifications/recompute remain gated to the exact `ivoryya` admin account.
- Captured answers preserve formatting, tables and available source links. Errors show reasons and guidance. Ordinary failed queries do not retry automatically; starting a new project scan checks all its queries. Selective retry is not implemented.

## Architecture

- `app/`, `desktop.py`: Windows agent, local FastAPI/SQLite state, browser profiles and provider adapters. Browser scans run on the user's PC across ChatGPT, Perplexity, Alice and Google.
- `server/`: central API, accounts, PostgreSQL, managed runs and billing. Managed checks use control-plane query UUIDs; local integer IDs remain for unmanaged runs. Pending uploads use the agent outbox.
- `frontend/`: React/Vite UI shared by the agent and web cabinet; built site assets live in `web/`.
- Production: `https://airate.tech`; screenshots in Yandex S3; semantic analysis via OpenRouter. GitHub Actions deploys `production` with backup/restore verification, serialized activation and readiness checks. Windows artifacts are published atomically through `scripts/publish-agent.py`.

## Open checks and limitations

- Windows release automation: PR #21 contains the full process; #20 registers the manual workflow on default branch `main`. Local EXE/installer/browser/reinstall/uninstall smoke and Linux PR CI passed. Dedicated non-root publishing account, download ownership, traverse-only parent ACL and pinned GitHub credentials are configured; live artifacts remain 2026.10.1.3. New-binary publication through Actions is unverified. See `docs/windows-agent-release.md`.

- Native upgrade of an existing user installation, WebView2/tray/Windows logon behavior and power-loss recovery still need validation on a real PC. Disposable updater fixtures passed; this does not verify the installed user's full scenario.
- A real provider scan with a clarification, historical S3 screenshot recovery, paid saved-answer recompute and a live PostgreSQL upload/recompute race remain unverified.
- Google completion uses a quiet-time heuristic. Preservation of a nonempty Google source list and sustained provider rate-limit behavior remain unverified.
- An off-VPS database backup destination is not confirmed; the delivery guide currently records VPS-local backups.

## Next action

Corporate mail: support/hello/noreply@airate.tech remain at REG.RU. SMTP.BZ is approved and enabled in production via connect.smtp.bz:2525 STARTTLS; final-container authentication returned 235. The approved demo HTML test to egorjojori@gmail.com was accepted and the user confirmed Inbox delivery. Existing REG.RU MX/DKIM were preserved; merged SPF, SMTP.BZ DKIM and stats CNAME were verified during setup. Tracking is disabled; transactional mode is enabled. Secrets remain in the private local SMTP file and production .env (0600). Earlier Aéza/REG.RU support ticket status was not rechecked.

Deployed: six-digit email code, ten-minute expiry, five wrong attempts, resend cooldown and serialized PostgreSQL email/IP sending limits. No account/wallet/session exists before proof; promo/connect errors roll back the complete registration. The cabinet restores pending confirmation after reload and explicitly offers Yandex registration. The approved HTML/plain-text template and embedded logo are connected to SMTP.BZ. Current password recovery still sends plain text. See [registration operation](docs/registration-email.md).

PR #60 is merged and deployed. Reviewed operator rehearsal and live migration preserved all prior rows/columns in 30 tables; the new queue was empty before workers started. A fresh backup was restored/verified before activation. Compatible fallback source 9b32129, image and checksum-verified archive are retained in /opt/airate/releases/mail-20261015. Final CI run 38685256024 attempt 2 passed; production SMTP/auth/recovery/readiness checks passed with no missing/invalid post-cutover notification rows. Detailed evidence is in the PR and private operator folder; local summary: build/mail-release-20261015/release-evidence.json.

Next: observe the first real paid top-up notification. No real payment or artificial balance credit was performed for this release. SMTP-uncertain/sending outcomes require provider-log inspection per docs/topup-emails.md; old paid orders are not backfilled.

The previous cloud scan completed all 300 provider tasks and reached done at 20:59 MSK on 2026-10-14 after PR #59 deployment. Older Windows notes in this checkout predate current production; consult the production branch for current runtime details.

## Checks and references

Read [AGENTS.md](AGENTS.md) for verification commands and review rules. Historical test counts describe earlier revisions; run checks appropriate to the current change.

- [Delivery, backups and rollback](deploy/DELIVERY.md)
- [Updater](docs/updater.md), [session preservation](docs/session-preservation.md)
- [Managed check identifiers](docs/managed-check-identifiers.md), [error diagnostics](docs/report-response-diagnostics.md)
- [Scan timing and benchmark](docs/scan-delays.md), [answer capture/rendering](docs/answer-readability.md)
- [Coinso integration](docs/coinso.md)
- [Historical release evidence](docs/project-state-history-2026-10-01.md) (read only for a specific investigation)

Prepared, not deployed: the user clarified the vidnal.ru report as a metric policy change. Absent AI blocks (`skipped`) now count as checks without mentions in cloud reports, comparisons and filters; technical errors remain excluded. Historical data recalculates on read without writes or paid rescans. Expected Yandex result for 2026-10-14: 10/29 = 34.5%. [Metric policy](docs/mention-statistics.md). Next: complete tests/review and publish the PR into production.

Aéza confirmed outbound SMTP blocking; reply draft is prepared but unsent because browser control stopped. REG.RU 465/587 still time out; SMTP.BZ remains active.
