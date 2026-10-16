# AIRate delivery

Production: https://airate.tech, VPS 45.146.90.88, Ubuntu 26.04 LTS.

The production environment variable `AIRATE_DEPLOY_HOST` selects the SSH host.
Its host key must match the pinned `AIRATE_KNOWN_HOSTS` environment secret.
`AIRATE_DEPLOY_KEY` belongs to the restricted `airate-deploy` user.
Never disable host verification during a move to another VPS.

Bootstrap uses `deploy/provision-ubuntu.sh` (Ubuntu 24.04 or 26.04 LTS).
Once the reviewed delivery files are installed in `/opt/airate/deploy`, run
`bash setup-delivery.sh /path/to/deploy-key.pub` as root. Start
`airate-backup.timer` after restoring the database and verifying a backup.

## Recovery on 28 September 2026

The old VPS was deleted by the owner before transfer. Recovery used a consistent
SQLite backup of the local account database, imported into a fresh PostgreSQL
database with `server.import_sqlite`. That importer verifies every table's row
count and canonical content in one transaction before committing. The snapshot
contained 1 admin account, 2 projects, 597 results, 1733 checks and 248 screenshot
records. The owner confirmed no newer scans or secrets existed on the old VPS.
Local Yandex, S3 and OpenRouter settings and the verified Windows downloads were
restored. Existing Yandex Cloud screenshot objects remain in their original
bucket. No secret or account snapshot belongs in Git or an application image.

Old VPS backups, TLS keys and server-only sessions could not be recovered from
the deleted machine. HTTPS certificates are issued anew. A session/device token
created only on the old VPS may require signing in or connecting the agent again.
The domain and OAuth callback remain unchanged.

## Release a website/API change

1. Work in a feature branch and push it. `Verify and deploy` runs backend checks and
   frontend checks in parallel. The frontend job uploads the tested `web/` build for
   the image job, which builds and smoke-tests one image from that exact output. The
   aggregate `Tests and build` check fails unless each of those jobs succeeds.
2. Open a pull request **into `production`**. The `Tests and build` check must
   pass with the branch up to date. Merge the reviewed change.
3. The production push repeats those checks and builds one Docker image tagged with
   the exact commit SHA on a GitHub-hosted runner. Only that trusted production run
   saves its smoke-tested image as a short-lived, SHA-named artifact; deploy verifies
   its SHA-256 before upload. A PR artifact is never reused after merge because the
   production SHA is built and checked again. The VPS does not need GitHub credentials
   or a repository checkout to receive releases.

4. An environment restricted to the production branch supplies the dedicated
   SSH key and pinned host key. The SSH account accepts only checksum-verified
   image uploads and deployment commands; it cannot open a shell or forward ports.
5. The server verifies the archive and image revision, compares migration heads,
   backs up PostgreSQL and restores that backup into an isolated temporary DB.
   The live database is never the restore target.
6. Uvicorn receives SIGTERM and has 150 seconds to finish requests; Docker waits
   180 seconds. There is a short availability gap during container replacement
   on this single-server installation. This is not zero-downtime deployment.
7. Readiness checks query the database, verify the release SHA and check HTTPS.
   A failed activation restores the previous application image and configuration.
   The database is never erased or automatically rolled back.

Docker's GitHub Actions cache can make a later build warmer; cold and warm cache
durations vary and are not a release-time guarantee. PRs may read the cache but only
trusted production runs export to the shared server-image cache.

Deployments are serialized (`cancel-in-progress: false` plus a VPS file lock).
Changing the Alembic head blocks unattended deployment before stopping the app.
Prepare a separately reviewed, backward-compatible migration for such releases.
Changes to Compose, Caddy or root-owned delivery scripts also require explicit
installation on the VPS; application-image delivery does not update these files.

`main` is not the production deployment branch. Feature/main/PR runs receive no
production environment secrets. Never use `pull_request_target` to build PR code.
GitHub environment/branch-protection availability for private repositories
depends on the account plan. Check those controls before changing visibility;
do not move environment secrets into unrestricted PR jobs as a workaround.

## VPS files and recovery

- `/opt/airate/deploy/.env`: secrets, mode 0600; never in Git or the image.
- `/usr/local/sbin/airate-ssh-gate`: restricted SSH entry point, root-owned.
- `/usr/local/sbin/airate-release`: deployment and rollback, root-owned.
- `/opt/airate/deploy/backups`: latest 30 verified database dumps + checksums.
- `airate-backup.timer`: daily 03:30 UTC, randomized by up to 10 minutes.
- `docker compose logs --tail=100 web`: application startup diagnosis.
- `systemctl status airate-backup.service`: most recent scheduled backup result.

Backups remain on this VPS until a **separate** private backup bucket and its
credentials are configured. Screenshot storage is not a database backup.
Application images retain the active and previous images plus recent releases.
On failed deployments, inspect the Actions log before manually retrying.
Transport failures after activation can make Actions red while the release is
already live: compare `/api/v1/ready` with the commit SHA before acting.

For manual rollback, select an existing `airate-web:<SHA>` image, preserve a fresh
backup, set `AIRATE_IMAGE` and `AIRATE_RELEASE` in the server `.env`, then run
`docker compose up -d --no-build --no-deps --wait web` and verify `/api/v1/ready`.
Only do this when the selected image supports the current database schema.

### Promo schema release on 14 October 2026

Production b3c1f3055e9a52dab8a216be7f0ee046742a6c91 uses
20261014_promo_codes. The previous 50f18ee image does not know this revision and
must not be selected for rollback. The retained image
`airate-web:promo-rollback-20261014` is built from tested 0274ab3 server/web sources
and the previous runtime dependencies; set AIRATE_RELEASE to
0274ab334d2b7efe799e6e7f4b1a3b401f8a2695 when using it. It supports the schema
and promo reservations/refunds. Upgrade, metadata check, canonical preservation
of 26 existing tables/columns and readiness without workers passed on an isolated
restored DB before the reviewed live upgrade. Live preservation was checked
before fallback startup; ordinary CI activation then retained its image ID.

One-off operator scripts/evidence stay in `/opt/airate/releases/promo-20261014`.
The live procedure admits only the old head, holds the release-lock, drains web,
creates/restores a backup, uses 5s lock/60s statement timeouts and refuses startup
if canonical preservation fails. It never restores or downgrades the live DB.
The migration-head gate and restricted CI access were not changed.
User-authorized persistent administrative SSH uses local alias `airate-admin`
with a dedicated private key and pinned host; forwarding is disabled. Credentials
stay in the user's SSH directory, outside Git. This does not alter release authorization.

## Retired Windows download

The Windows agent is retired. Website/API releases do not build, publish or test
an installer; keep shared server deployment backup, restore, migration-head,
readiness and rollback gates intact.
