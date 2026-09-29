# Agent update release

`app.__version__` is the one release version. Build the EXE first; it writes `agent-version.txt` into the bundle. `build-installer.ps1` reads that marker and rejects an explicitly different version.

After the installer and portable ZIP are built, `build-installer.ps1` runs `write-release-metadata.ps1` and writes `dist/agent-release.json` with their sizes and SHA-256 values. Publish with `python scripts/publish-agent.py --host root@45.146.90.88 --key C:/Users/ego/.ssh/airvision_aeza_ed25519 --dist dist`.

The publisher uses a Linux flock, unique upload stages, immutable version directories, and an atomic `agent-current` pointer. `agent-previous` points to one coherent earlier release. Version folders stay available for rollback; prune old folders manually when storage requires it. Agents released before this updater need one manual upgrade: installer for installed mode, ZIP for portable mode. Quit through the tray menu before replacing portable files and preserve `data`.

The public update endpoint exposes a release only when the manifest has the required shape and both fixed artifacts match its recorded sizes. Desktop agents use fixed HTTPS download URLs and never read URLs from the manifest.

Checks: `python -m pytest tests/test_updates.py tests/test_agent_publication.py tests/test_desktop_login.py server -q`, then frontend test/lint/build. Publication interruption and concurrency checks require Linux; CI runs them. The loopback fixture `scripts/frontend_smoke_server.py` reproduces dialog dismissal, manual reopening, offline checks, withdrawal and later releases without real scans or accounts. Native tray focus and actual installer replacement need a Windows smoke check.
