# AIRate current project state

Updated 2026-09-29. Repository: egotrippingh/aiparser; deployment branch: production.

## Report response diagnostics — in verification

- Agent candidate 2026.9.29.6 sends nullable error_message, including one historical page per heartbeat via separate account/device cursor and server ACK. Server enrichment atomically fills only NULL reasons for matching failed results; status, answer, billing and sources stay unchanged.
- All answer views share safe paragraphs/lists/HTTP(S) links and a visible source block. Error reasons and honest guidance explain that ordinary errors do not retry automatically and a new project run checks all queries.
- User's WEB-PM HTML confirmed Perplexity free-search quota. Adapter now recognizes the limit heading; existing three-strike service stop remains. Exact provider recovery timing and live login/scan are not tested; current user's scan remains untouched.
- Scope excludes selective retry and restoring missing answer text. Source fixes passed independent Sol + Astra reviews. Server suite 54 passed before the owned-link repair; final affected server checks 7 passed, frontend 31 passed plus lint/build and browser desktop/360px proof. Full agent regression 102 passed, 2 skipped; GitHub feature and PR CI passed on source 31b50ed8ba28d3810c0dbfce9fb460b050e8fbb1 (PR #11). Verified backup backups/aiparser-20260929T120314Z-243739.dump and isolated PostgreSQL clone proof passed: core fingerprints unchanged, old image starts after clean downgrade, compatibility rollback preserves diagnosis. Compatibility and staged candidate images are prepared under /opt/airate/staging/diagnostics-31b50ed. Live schema/app remain unchanged; idle window requested for promotion then ordinary CI deployment. Windows 2026.9.29.6 bundle self-test passed; installer/public download verification pending.

## In-app updater — release 2026.9.29.5

- The agent verifies a freshly fetched official installer before handoff, blocks new work while updating, and uses an installer process handle to wait for graceful exit; a matching next-launch result removes only its own temporary stage. Installer and portable modes share the same file update path. Failed cancellation keeps the parent alive until the installer exits; retries clear the cancellation latch and stale errors. The installer writes its version marker last and attempts fallback relaunch after replacement failure.

- Evidence: 31 updater/admission checks cover real endpoint/poll/login concurrency and disk/handoff failures; 75 selected agent checks and 28 frontend checks, lint/build passed in build/qa/internal-update-20260929-03/report.json on the reviewed working tree; final commit checks are recorded in the release PR. Independent Sol/Astra reviews found and confirmed repairs for server/tray shutdown, admission races, late failure watcher, denied cancellation and version-marker ordering. Native fixture report build/native-update-fixture/native-run-lw4kbfk3/report.json passed five scenarios without changing production installation registration. Disposable browser fixture covers download progress, ESC blocking, error/retry and restart. Final release PR records final source checks, packaging and publication. No existing-user native update, provider scan or power-loss rollback test was performed.

## Managed check identifiers — release 2026.9.29.4

- Managed runs use control-plane query UUIDs consistently for reservation, server analysis, arbitration, settlement, screenshots, recovery, recheck, and result export. Local integer IDs remain for unmanaged runs.
- Before flushing, a transactional local repair remaps only proven legacy local-ID outbox rows owned by the connected account. Billing and screenshot senders retain and exclude known foreign, missing-map and conflicting managed work. Interrupted recovery respects ownership and existing conclusive statuses. A paused remote run is shown as paused even without a local controller, without resuming it locally.
- Evidence: 52 server tests, 37 selected agent checks, 28 frontend checks, lint/build passed in build/qa/managed-checks-20260929-02/report.json. The first broad local run timed out at 180 seconds; the final server suite completed at 219 seconds under a 360-second bound. Real TestClient/disposable databases verified one charge after old local-ID repair, retry/new-assignment flow, rollback and the actual scanner model/arbiter/result IDs. Sol and Astra independent reviews found conflict/owner/UI defects; repaired and final reviews passed. Browser fixtures verified remote pause with/without controller, waiting for sync and resumed status; screenshot build/agent-pause-final.png is synthetic. No real provider scan or remote WEB-PM queue test was run. The release PR records final packaging, CI and live download evidence. Procedure: docs/managed-check-identifiers.md.

## Session preservation — release 2026.9.29.3

- Branch `fix/agent-session-recovery` keeps an installed build on its established `%LOCALAPPDATA%/AIParser` data directory. On the first installed launch only, it reuses a writable legacy `BASE_DIR/data` when that folder contains user state and the installed location does not. It never merges or overwrites locations.
- Startup checks saved cookies for every supported service before the local API starts, without opening a browser or contacting a provider. Unreadable state does not select a different data folder; the UI distinguishes saved, missing, expired and unreadable sessions. Actual provider acceptance remains the next scan. Unknown former locations require explicit profile transfer.
- Local recovery restored five profiles after browser shutdown, retaining the source and a complete destination backup. The installed agent API confirmed all five saved sessions. A requested ZIP export was written only to the user's desktop and passed ZIP integrity verification.
- Evidence: 50 focused Python checks passed (two Linux publication skips); 27 frontend checks, lint/build and fixture session states passed. Independent Sol/Astra reviews found access-error fallback defects; both repaired and rechecked. Logged runs: build/qa/sessions-final-20260929-02/report.json and build/qa/sessions-final-20260929-03/report.json. Procedure/limitations: docs/session-preservation.md. The release PR records final packaging, CI/deployment identity and live download evidence. Installer target: 2026.9.29.3.

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

Updater native WebView2 click-to-relaunch on an existing user profile remains unverified; disposable installed/portable replacement passed five native fixture cases. Publication retains version folders; prune older directories manually when storage requires it, keeping current and previous intact.

Use feature branches and reviewed, tested PRs into production; GitHub Actions handles backup, serialized deployment, graceful shutdown and readiness. Do not commit .env, data, browser profiles, build or dist. Secrets remain in existing local/server storage; this file contains no credentials.
