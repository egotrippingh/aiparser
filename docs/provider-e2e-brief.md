# Provider E2E brief

- Google target run 1/100 is still running after 88 minutes; remote version remains unknown.
- Alice's known verified clone completed three checks with full texts (2928/2650/3048 characters) and 18/12/13 sources. The new authenticated selector matched logged-in fallback probes 2/3 and never matched the logged-out guest control; the first fallback probe was not ready, so this is not a claim for every profile.
- Google local baseline completed 3/3 stably.
- ChatGPT local Firefox profile requires login; remote authenticated E2E remains unverified. Guest IAB DOM was verified independently during streaming and after two completed responses.
- Screenshot top cropping/faded stitched lines and Google citation extraction remain open checks. Final build evidence is recorded below.

## Implementation and acceptance

- Alice accepts any visible authenticated marker, including the new account name inside the hybrid sidebar trigger; cookies/input alone never grant readiness.
- ChatGPT's visible login form reports `auth_required`; unknown/hidden pages remain errors. New composer/message markup is supported. Completion checks the latest message's owning new-role container for `data-message-complete` (including its empty value), otherwise retains legacy visible feedback markers; an older completed message cannot finish a streaming new-role response.
- Fresh ask/capture has a 900-second total deadline. Timeout records one retryable error and leaves the service tail pending, including when context shutdown also fails.
- Operator stop interrupts ask; a capture already underway finishes under its remaining original deadline before its returned evidence is persisted. Stop can therefore wait up to that deadline during capture. Previously persisted answers drain normally.
- Cancellation-resistant tasks retain ownership until completion. Context teardown waits 10 seconds, cancellation waits five, and existing profile-scoped cleanup runs; no other browser profiles are killed.
- Phase snapshots are per service, use monotonic elapsed time and omit query text. Control polls include the agent version. Local pause/resume/stop endpoints execute on the event loop.

## Evidence

- Isolated **headless local pipeline**: real Google and Alice, three identical queries each, parallel browser capture, SQLite persistence, rule analysis and six readable WebP exports. All six completed in **89.08 seconds**, no pending captures, billing disabled. This did not test paid cloud analysis or the remote PC.
- Earlier headful pipeline returned Alice auth errors; the new sidebar fallback passed two of three isolated readiness probes. Broad readiness across profiles/modes is not qualified.
- `python -m pytest tests/test_browser_watchdog.py tests/test_scan_pipeline.py tests/test_scan_retry.py tests/test_alice_readiness.py tests/test_chatgpt_recovery.py -q`: **49 passed** on the final product revision (including the early-stop guard and ChatGPT completion compatibility). Checks cover actual scan finalization/analysis drain, capture/stop races, resistant cancellation, source completion after stop, per-service phases, HTTP control threading and bounded/error shutdown.
- CI includes the new regression modules. Independent correctness and risk reviews found the repaired watchdog paths acceptable; final checks and publication evidence follow below.

- Supplied remote logs: `agent (2).log` covers 2026-10-07 05:52–15:26 Moscow. It records 28 ChatGPT completion-marker timeouts of 240 seconds (112 minutes of timeout waiting). The first Google answer was persisted and its screenshot uploaded; the next hung browser substep is not identified by these logs.
- Latest remote database snapshot: Alice 100 auth errors; Google 1 answer (2361 characters); ChatGPT 29 text answers; Perplexity 9 text answers and 91 limit results. Current run has no `skipped` results, so a dash in the interface cannot alone identify absence of an AI block.
- New ChatGPT guest DOM: streamed second answer (15 characters) had no completion attribute while the prior answer (4148 characters) did; after completion the second answer (12691 characters) acquired the attribute. Page state independently reported streaming/complete transitions. Authenticated remote variants and temporary-chat detection remain unqualified.
- Server suite: **74 passed**. Broad single-process agent collection failed (65 failures before the final completion-only change); a pristine HEAD baseline independently reproduced the same first three API smoke failures. Do not report the broad collection as passing; CI runs its required modules in separate groups.

## Published delivery

- [PR #30](https://github.com/egotrippingh/aiparser/pull/30) merged as `091f1908e71bfa5300a17884988677446097031f`. [PR checks](https://github.com/egotrippingh/aiparser/actions/runs/37623311897) and [production checks/deploy](https://github.com/egotrippingh/aiparser/actions/runs/37623664538) passed, including required agent groups, server tests, frontend tests/build, database backup/isolated restore and public readiness.
- Windows **2026.10.7.2**, bundle `AI-Mentions-Windows-20261007-154323`, includes the final ChatGPT completion fix. Six changed packaged Python modules and packaged selectors were compared against final source; source directories match the merged production revision.
- Native EXE/browser self-test, isolated installation, installed browser self-test, same-version reinstall and uninstall passed. **3662 files** matched the bundle/browser inputs; both current and legacy data sentinels survived reinstall/uninstall. Private test output: `build/installer-smoke-up1mrqiw`.
- Installer: **470190738 bytes**, SHA-256 `52bd419eb8b5b218163fbee57e4e19ee3cef1c960b3835ff95eb98091f8f3fa6`.
- Portable: **122350637 bytes**, SHA-256 `148dc9c89c4928c644470b0a1c4ea563840a65ece10496ce342af3ebd1e20b60`.
- Metadata and complete public HTTPS downloads/hashes passed from the VPS. The operator-PC installer prefix matched; a complete operator-PC download remains unqualified. No user profiles/logs/QA files were packaged; the archive's sole database is the bundled Camoufox WebGL resource.
- Release activation retained **2026.10.7.1** as previous. A first SSH attempt timed out before staging; retry completed verified staging and atomic activation. No data/schema migration or profile reset.
- Required follow-up: update WEB-PM ЕГОР to 7.2 and rerun a small identical set. These local and guest-DOM checks do not establish successful authenticated remote E2E, sustained throughput, complete Google citations or full stitched-image quality.
