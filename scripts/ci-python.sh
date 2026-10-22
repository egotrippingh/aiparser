#!/usr/bin/env bash
# Canonical GitHub Actions Python matrix. Nested AGENTS.md gates stay local;
# keep this file and .github/workflows/delivery.yml in sync when grouping changes.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
if command -v python >/dev/null 2>&1; then
  py=python
else
  py=python3
fi
"$py" -m pytest server -q
"$py" -m pytest tests/test_telemetry.py -q
"$py" -m pytest tests/test_brand_clarification.py -q
"$py" -m pytest tests/test_scan_pipeline.py -q
"$py" -m pytest tests/test_xmlriver.py tests/test_xmlriver_text.py tests/test_rules.py tests/test_llm_parse.py -q
"$py" -m pytest tests/test_abandon_saved.py tests/test_billing_client.py tests/test_screenshot_storage.py tests/test_humanize.py -q
"$py" -m pytest \
  tests/test_updates.py tests/test_update_admission.py tests/test_agent_publication.py \
  tests/test_desktop_login.py tests/test_profiles.py tests/test_login_feedback.py \
  tests/test_data_paths.py tests/test_main_session_check.py tests/test_billing_recovery.py \
  tests/test_agent_live_sync.py tests/test_perplexity_diagnostics.py tests/test_readable_capture.py \
  tests/test_scan_plan.py -q
"$py" -m pytest tests/test_service_timing.py tests/test_alice_wait.py tests/test_google_wait.py -q
"$py" -m pytest tests/test_browser_watchdog.py tests/test_alice_readiness.py tests/test_chatgpt_recovery.py tests/test_scan_retry.py -q
# Separate processes: several modules mutate config.DB_PATH at import time, so a
# single `pytest tests` collection shares one SQLite path and fails baseline checks.
"$py" -m pytest tests/test_api_smoke.py -q
"$py" -m pytest tests/test_overview.py -q
"$py" -m pytest tests/test_adapters_base.py tests/test_alice_sources.py tests/test_arbiter.py -q
"$py" -m pytest tests/test_browser_install.py tests/test_browser_install_progress.py -q
"$py" -m pytest tests/test_deep.py tests/test_external.py tests/test_imaging.py tests/test_managed_llm.py -q
"$py" -m pytest tests/test_mentions_export.py -q
"$py" -m pytest tests/test_parallel.py -q
"$py" scripts/benchmark_scans.py --self-check
bash -n deploy/release.sh deploy/ssh-gate.sh deploy/provision-ubuntu.sh deploy/setup-delivery.sh deploy/backup.sh deploy/verify-restore.sh
