# AIRate current project state

Updated 2026-09-29. Repository: egotrippingh/aiparser; deployment branch: production.

## Delivered source

- Agent release 2026.9.29.2 adds account-independent startup/hourly release checks, an update dialog, manual check, dismissal persistence and fixed official download targets. Older distributed EXEs require one manual upgrade to acquire this feature.
- Build version comes from app.__version__ through the bundle marker and installer. scripts/publish-agent.py verifies both remote artifacts and activates one immutable release directory atomically under a Linux lock; agent-previous retains a coherent rollback target. Download responses pin immutable files.
- Cabinet drafts guarded across Account, logout and hash history; mutation frozen during save; stale screenshot response discarded.
- Requested landing captions removed; service row uses local 30x30 logos.
- Agent settings always visible; manual opening and successful login retain the window. Explicit background launch with a device token starts in tray. Initial polling error shown and cleared on recovery. X hides; tray Quit exits.

## Evidence and delivery

Updater brief/procedure: docs/updater.md. Local final checks: 52 server tests, 26 frontend tests, 20 updater/publication/login tests passed; two publisher tests require Linux and are included in GitHub Actions. Logged runs: build/qa/updater-final-20260929-01/report.json and build/qa/updater-frontend-final-20260929-02/report.json. Browser fixture verified automatic/manual notice, Later/ESC, no-login portable mode, subsequent release, withdrawal, failed state refresh after dismissal and clearing stale errors; no real accounts or scans used. Independent Sol and Astra reviews completed and confirmed findings repaired. Linux disposable-directory interruption/retry/concurrency probe passed; Astra also checked 94 in-memory failure cases.

Updater publication uses feature branch feat/agent-update-notice. Its release PR records final source/deployment identity, installer checksum and live smoke evidence. Installer target version: 2026.9.29.2; Camoufox bundle remains 152.0.4 beta.30.

Task briefs and reproducible fixture: docs/frontend-hardening.md, docs/landing-agent-cleanup.md, scripts/frontend_smoke_server.py.
26 frontend checks, lint and build passed; 3 desktop login tests passed. Independent Sol and Astra reviews completed; findings repaired. Logged run: build/qa/frontend-final-20260929-03/report.json. GitHub Actions checks passed for source 103c2b1.

Release PR: https://github.com/egotrippingh/aiparser/pull/6 . Its final delivery note contains the merge revision, CI deployment outcome and installer checksum. Live deployment identity is exposed by https://airate.tech/api/v1/ready . Installer version: 2026.9.29.1, bundled Camoufox 152.0.4 beta.30. Packaging sources exclude user data and secrets. EXE build's self-test passed.

## Unverified / future checks

Native WebView2 window-close/tray/Windows logon interaction and 430x600 rendering; real native confirm dialog appearance; mobile viewport (IAB override stayed at measured 1280px). These are not claimed as verified. No new payment, real AI scan or real service-login tests were run for this frontend work.

Updater native tray focus and actual installer/portable replacement on an existing user profile remain unverified. Publication retains version folders; prune older directories manually when storage requires it, keeping current and previous intact.

Use feature branches and reviewed, tested PRs into production; GitHub Actions handles backup, serialized deployment, graceful shutdown and readiness. Do not commit .env, data, browser profiles, build or dist. Secrets remain in existing local/server storage; this file contains no credentials.
