# Windows agent rules

Read root `AGENTS.md`. These rules also apply to agent tests and build scripts.

- Provider browsers run on the client PC. Local API stays on loopback; do not publish
  it as the account server. Accounts/runs belong to the server; the agent executes them.
- Trace orchestrator → adapter → `app/db/repo.py` → `app/billing.py` before changing a
  scan transition. Capture must be durable before asynchronous analysis/upload.
- Resume uses frozen query/brand/settings, payer and check IDs. Preserve pending evidence,
  outbox retries, once-only settlement and terminal abandonment; do not resurrect work.
- Stop/pause/cancel are different states. Preserve underway captures and saved work;
  bounded queues/timeouts and resource cleanup are mandatory. Do not use blocking I/O
  or sleep on the event loop, unbounded tasks/retries or swallowed cancellation.
- Adapter failure/auth/captcha/throttling is not a negative brand result. Completion
  and readiness must be proved for the current answer; retain provider pacing defaults
  unless actual measurements support changing them. Keep `playwright<1.61` compatibility.
- Never test against or replace real `data/`, `%LOCALAPPDATA%/AIParser`, browser profiles
  or credentials. Use temporary directories. Unknown cookie state is not logged-in proof.
  Updates/uninstall must preserve user data; do not downgrade a changed local schema.
- Reuse adapter interfaces and readable-answer helpers. Fix shared callers together.
  No speculative multi-account/browser concurrency or rewritten scanner architecture.

## Checks (from repository root, with the project Python)

Run the nearest `tests/test_*.py` regression first, then the affected group below in a
separate pytest process. Add sibling tests for each changed shared caller.

- Scan/durable data/billing:
  `python -m pytest tests/test_scan_pipeline.py tests/test_abandon_saved.py tests/test_billing_client.py tests/test_billing_recovery.py tests/test_screenshot_storage.py -q`
- Provider readiness/timing:
  `python -m pytest tests/test_browser_watchdog.py tests/test_alice_readiness.py tests/test_chatgpt_recovery.py tests/test_scan_retry.py tests/test_service_timing.py tests/test_alice_wait.py tests/test_google_wait.py -q`
- Sessions/update/data paths:
  `python -m pytest tests/test_updates.py tests/test_update_admission.py tests/test_agent_publication.py tests/test_desktop_login.py tests/test_profiles.py tests/test_login_feedback.py tests/test_data_paths.py tests/test_main_session_check.py -q`
- Detection: `python -m pytest tests/test_rules.py tests/test_llm_parse.py tests/test_brand_clarification.py -q`
- Throughput changes: also `python scripts/benchmark_scans.py --self-check`; compare the
  same workload/settings before and after. Synthetic timing is not live throughput.

These groups do not replace the full CI matrix before release. Broad single-process
agent collection has known baseline failures: reproduce an encountered failure on the
unchanged base before calling it unrelated; do not disable it or claim the suite passed.
For an actual Windows release, follow `deploy/DELIVERY.md` EXE/browser and isolated
installer lifecycle checks; Python tests alone do not qualify an installer.
