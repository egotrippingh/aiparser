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

1. Work in a feature branch and push it. `Verify and deploy` runs backend tests,
   frontend tests, a production frontend build and shell syntax checks.
2. Open a pull request **into `production`**. The `Tests and build` check must
   pass with the branch up to date. Merge the reviewed change.
3. The production push runs checks again, then builds a Docker image tagged with
   the exact commit SHA on a GitHub-hosted runner. The VPS does not need GitHub
   credentials or a repository checkout to receive releases.
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

## Windows download

Use the manually dispatched **Build and publish Windows agent** workflow for a release. It builds fixed artifacts on Windows and only publishes when the site readiness revision equals the workflow source SHA. Operations must first create the dedicated non-root publisher account with ownership of `/opt/airate/deploy/downloads`, its lock, `agent-releases`, and the current/previous aliases; it must have no sudo access. Configure a pinned host key plus `AIRATE_AGENT_PUBLISH_KEY`, `AIRATE_AGENT_KNOWN_HOSTS`, and `AIRATE_AGENT_PUBLISH_HOST` in the production environment. Do not reuse `AIRATE_DEPLOY_KEY`. Current cloud credentials are not configured, so this automation is prepared but not verified live.

Build on Windows with `scripts/build-exe.ps1 -AccountUrl https://airate.tech`.
The script builds the frontend, bundles the AIRate icon, runs EXE self-tests,
removes the self-test database and produces `dist/AI-Mentions-Windows-latest.zip`.
Check the archive's `account-url.txt` and ensure no user data or `.env` is present.
Publish the installer, ZIP and manifest together through `scripts/publish-agent.py`,
as the workflow does. It verifies uploads and switches the complete release atomically.
Do not restart the application just to publish a new ZIP.

### Single-file installer (primary download)

Install Inno Setup 6.7.3 from JRSoftware (winget package `JRSoftware.InnoSetup`).
After the verified portable build, compile its clean release directory:

```powershell
./.venv/Scripts/python.exe scripts/prepare-browser.py
./scripts/build-installer.ps1 -BundleDir ./dist/AI-Mentions-Windows-YYYYMMDD-HHMMSS -BrowserDir ./build/browser-runtime/camoufox-152.0.4-beta.30 -Version 2026.9.28.1
```

The installer includes the official Windows x64 Camoufox distribution. The
preparation script pins its release and verifies the publisher's SHA-256 before
extracting it; it never reads browser profiles from the builder's PC. Browser
files install under `{app}/browser`, along with the agent, with wizard progress.
The agent validates and uses that browser immediately, with an explicit Firefox
version, even when the user's Camoufox cache is empty. No separate browser install
button is needed on a healthy installation. The existing download/repair path
remains available for portable builds or a damaged browser installation.

This produces `dist/AIRate-Setup-latest.exe` and a versioned installer. Publish
the complete release through the same publisher **before** deploying a homepage
that links to it. The API discovers it beside `AGENT_DOWNLOAD_FILE`,
or at the optional `AGENT_INSTALLER_FILE` path. No restart is needed for later
installer updates. Keep the previous installer for rollback.

Primary public download: https://airate.tech/downloads/AIRate-Setup.exe.
The cabinet download API prefers the installer when present. The portable ZIP
URL remains available for existing users.

The per-user installer allows choosing a directory (default
`%LOCALAPPDATA%\Programs\AIRate`), creates Start menu/optional desktop shortcuts
and an uninstaller. `installed-mode.txt` selects `%LOCALAPPDATA%\AIParser` for
account data and profiles; updates/uninstall do not erase that directory or the
separate Camoufox cache. Existing portable ZIP data remains in its old location;
users switching from portable to installed should close the old agent and sign
in again. Projects/reports remain in their website account. Close the running
agent via the tray before updating. Autostart remains opt-in inside the agent;
uninstall removes only an autostart entry pointing at this installation.

Use `build-exe.ps1 -TestBrowser` to exercise both frozen browser launch paths
against a disposable addon cache with a missing manifest. AIRate deliberately
excludes Camoufox's optional default extensions; no addon download is required.

Windows signing is not configured; the installer and agent are unsigned.

Before publishing, run the Windows installer lifecycle test (requires no AIRate
installer already registered on that Windows account):

```powershell
./.venv/Scripts/python.exe -X utf8 scripts/test-installer.py --installer ./dist/AIRate-Setup-latest.exe --bundle ./dist/AI-Mentions-Windows-YYYYMMDD-HHMMSS --browser ./build/browser-runtime/camoufox-152.0.4-beta.30
```

It checks every installed agent/browser file against the clean bundles, runs
the installed EXE and bundled browser with isolated app data, reinstalls,
uninstalls, and verifies that the test data survived. It creates no shortcuts
or agent windows; a disposable browser test window briefly opens. Test logs
remain under `build/installer-smoke-*`.
