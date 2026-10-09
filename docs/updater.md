# Agent update release

`app.__version__` is the one release version. Build the EXE first; it writes `agent-version.txt` into the bundle. `build-installer.ps1` reads that marker and rejects an explicitly different version.

## In-app update

The agent downloads only the fixed HTTPS installer URL after refetching release metadata. It checks the advertised byte count and SHA-256 before spawning the installer. This is integrity checking, not a publisher signature.

The updater rejects new work while it is preparing an update and only proceeds when no scan, browser install, or login is active. The installer receives the current process PID, absolute executable directory, mode, acknowledgement path, and result path. It acknowledges only after opening a process handle, then waits for the old process to exit without forcing it. Installed and portable updates use the same installer; portable mode writes files in place without adding installer registration or shortcuts. User data remains outside the update file set.

A successful next launch records and consumes its matching ASCII result marker, then retries removal of only its own uniquely named temporary stage if Setup still holds the executable open. Partial downloads before installer launch are removed. Failed installer stages remain for diagnostics; no generic cleanup traverses user folders. A replacement failure reports an ASCII result and attempts to relaunch the existing target; it does not guarantee recovery from power loss or a mixed file transaction.

After the installer and portable ZIP are built, `build-installer.ps1` runs `write-release-metadata.ps1` and writes `dist/agent-release.json` with their sizes and SHA-256 values. Publish with `python scripts/publish-agent.py --host root@45.146.90.88 --key C:/Users/ego/.ssh/airvision_aeza_ed25519 --dist dist`.

The cloud release path is the **Build and publish Windows agent** workflow,
dispatched on `production` with `publish=true` after the same site revision is
live. It uses a dedicated non-root publisher and pinned SSH host key, and
verifies both complete HTTPS downloads. The Windows job also runs XMLRiver
offline render checks with the freshly prepared pinned browser.

The publisher uses a Linux flock, unique upload stages, immutable version directories, and an atomic `agent-current` pointer. `agent-previous` points to one coherent earlier release. Version folders stay available for rollback; prune old folders manually when storage requires it. Agents released before this updater need one manual upgrade: installer for installed mode, ZIP for portable mode. Quit through the tray menu before replacing portable files and preserve `data`.

The public update endpoint exposes a release only when the manifest has the required shape and both fixed artifacts match its recorded sizes. Desktop agents use fixed HTTPS download URLs and never read URLs from the manifest.

Checks: `python -m pytest tests/test_updates.py tests/test_update_admission.py tests/test_agent_publication.py tests/test_desktop_login.py server -q`, then frontend test/lint/build. Publication interruption and concurrency checks require Linux; CI runs them. The loopback fixture `scripts/frontend_smoke_server.py` reproduces dialog dismissal, manual reopening, offline checks, withdrawal and later releases without real scans or accounts. A Windows fixture compiled from the same installer source with a distinct QA identity verified installed/portable replacement, data/account URL preservation, parent timeout, cancellation after acknowledgement, and a locked EXE failure with old version retention and fallback relaunch. Native report: `build/native-update-fixture/native-run-lw4kbfk3/report.json`. The full existing-user WebView2 click-to-relaunch flow remains unverified.

## Failure and acceptance boundaries

No update proceeds during an active scan, session login, browser installation, account enrollment or control poll/maintenance operation. Admission and reservation share the existing scan lock. New operations are rejected until the update or its cancelled installer ends. A download failure permits retry; checksum/size mismatch never launches Setup.

The local API shuts down before the native window exits. A shutdown timeout cancels installation, retains the window, and restarts the API only after its old server thread ends. An indefinitely hung lifespan still requires manual recovery. If the abort file cannot be written, tray Quit waits for that installer to exit so normal parent exit cannot authorize a cancelled update. Forced termination by the OS is outside this guarantee.

Acceptance: one click in the update dialog downloads and verifies the official installer, shows progress, prevents duplicate clicks/ESC dismissal during application, preserves data, and relaunches the same mode/target. The installer writes its version marker last. The strongest limitation of reusing Inno Setup is lack of guaranteed rollback after power loss or arbitrary partial dependency replacement. Hash verification does not replace a digital publisher signature.

Disposable UI scenario: offer → Update → download progress (buttons disabled, ESC retains dialog) → injected failure → retry → restart. It never downloads or executes a real installer. Native replacement tests use benign fixture executables and disposable data, not the user's profiles. Agents older than 2026.9.29.5 require one manual bootstrap upgrade.
