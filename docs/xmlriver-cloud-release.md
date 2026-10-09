# XMLRiver server release

This procedure requires administrator access to the production VPS. The restricted
CI SSH account accepts image upload/deployment only; it cannot install Compose,
edit secrets or migrate the database. Do not merge production PR #35 until this
release's schema and server configuration are ready.

## Candidate and configuration

- Use the reviewed, CI-passing commit and its checksum-verified image. CI verifies
  that the server image imports without desktop/browser dependencies.
- Install the four XMLRiver environment entries from `deploy/compose.yml` and
  `deploy/.env.example` into `/opt/airate/deploy`. Populate the existing private
  `.env` with the stored XMLRiver access, without printing values or replacing
  unrelated configuration. Google region `213` needs no custom location mapping.
- New schema head is `20261009_server_captures`, following
  `20260929_result_error_message`. Existing rows default to phase `agent`;
  new cloud results have no device/local IDs. No existing answers are deleted.

## Database and activation

1. Schedule maintenance and stop new checks. Drain active agent/server work before
   stopping the application; keep the database and proxy running.
2. Run the existing `deploy/backup.sh`. It verifies restoration into an isolated
   database before retaining the backup. Keep the verified pre-migration archive.
3. Separately restore that archive into another disposable PostgreSQL database.
   Run the candidate's `python -m server.migrate` against that isolated database,
   then validate its Alembic head, retained users/wallets/checks/results and new
   constraints. Never point a restore test at the live database.
4. With writes still stopped, run the same reviewed migration against production
   using the candidate image. `python -m server.migrate` reads `DATABASE_URL` from
   the process environment; do not pass a password in command arguments or logs.
5. Activate the exact candidate and installed Compose configuration. Verify
   `/api/v1/ready` against its SHA, Google/Yandex collection without a computer,
   structured answer/product images, and a mixed run's subsequent agent phase.
   Use the authorized pilot budget; record actual provider/model costs separately
   from fake-service test evidence.

The existing unattended schema-head gate remains enabled. A schema migration
needs an operator-controlled activation, not a bypass of `deploy/release.sh`.

## Recovery boundary

Do not automatically downgrade or restore the live database. The previous image
does not contain the new Alembic revision and cannot be assumed to start against
the migrated database. If candidate activation fails, keep maintenance enabled
and repair/redeploy compatible application code on the same schema. Any live
database restoration requires a separate decision and a verified recovery plan.

Local SQLite tests establish behavior and migration metadata parity; they do not
establish PostgreSQL concurrency, real provider billing or successful deployment.
