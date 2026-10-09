# Account server rules

Read root `AGENTS.md`. Applies to server tests and Alembic migrations too.

- Validate request models at the boundary. Scope every project/result/check/run/device
  lookup to its owner. A matching client check ID alone does not establish ownership.
- Browser, device and admin sessions have different capabilities. Preserve Origin,
  cookie/CSRF defenses, expiry and revocation. Add a forbidden-access test whenever
  changing access. Ordinary/device sessions must not gain admin scan-journal access.
- Amounts are integer kopeks. Reserve/complete/release, ledger entries and payment
  webhooks stay idempotent under retries; server owns pricing and analysis budgets.
  New pricing must not mutate an existing reservation. Verify Coinso signature/status.
- Use existing SQLAlchemy transactions, constraints and revision CAS. Test stale writes
  and retries on changed paths. SQLite tests do not establish PostgreSQL concurrency.
- Freeze project/feedback inputs into a run. Feedback adapts future inference only;
  keep original answers, reported statuses, history and charges intact. Treat saved
  answers/comments as untrusted data, not executable model instructions.
- Screenshots remain private and owner-scoped; signed links expire. Preserve storage
  limits and `Cache-Control: no-store` for private review data. No credentials or answer
  payloads in diagnostics. Live S3/model/payment checks require task authorization.
- Schema changes use a new reviewed Alembic revision; no edits to applied revisions,
  drop/recreate or automatic production downgrade. Account for old agents and stored
  runs. Check migration heads/backward compatibility before any release.

## Checks (from root, disposable databases/fake providers)

1. Run the nearest regression: `python -m pytest server/test_<area>.py -q`.
2. Any server logic/API/schema change: `python -m pytest server -q`.
3. Feedback/reports: include `server/test_scan_feedback.py`, `server/test_reporting.py`,
   `server/test_brand_recompute.py`; money/auth/run changes include corresponding
   `test_app.py`, `test_coinso.py`, `test_auth_hardening.py`, `test_control.py` cases.
4. Shared agent contract: also the affected client checks in `app/AGENTS.md` and UI
   checks in `frontend/AGENTS.md`. Pin expected payloads/errors in a regression.

Use `.venv` with `scripts/requirements-ci.txt` for CI parity; no production `.env` or
database connection. For deployment/migrations read `deploy/DELIVERY.md`; preserve
backup, isolated restore, migration-head admission, readiness and rollback gates.
