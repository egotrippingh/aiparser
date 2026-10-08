# Scan pipeline publication, 7 October 2026

Published server and Windows agent **2026.10.6.1** from merged production source
`650e60b53ba36d2249bc83301256336bcf0c1d9e`, [PR #26](https://github.com/egotrippingh/aiparser/pull/26).
The implementation scope and deterministic checks are in [the capture brief](scan-pipeline-brief.md).

## Server

[Production run 37531443115](https://github.com/egotrippingh/aiparser/actions/runs/37531443115)
passed tests/build and deployment. Actual deployment logs confirmed a backup
`backups/aiparser-20261006T210852Z-1962970.dump` and successful restoration into
an isolated database before activation. Public `/api/v1/ready` returned the
merged source SHA; the homepage returned HTTP 200. No schema migration changed.

## Windows artifacts

The clean merged checkout built the EXE with production account URL and
`-TestBrowser`. The current release's Sentry sidecar was preserved before the
final installer/ZIP checks. Python 3.12.10, PyInstaller 6.22.3 and Inno Setup
6.7.3 were used. Camoufox 152.0.4 beta.30 was extracted only after checking its
pinned publisher checksum. No user profiles or account data were packaged.

The final installer lifecycle verified **1,819 files**, installed EXE/browser
self-tests, same-version reinstall and uninstall preserving isolated current
and legacy data. This does not prove upgrading an older real installation.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer | 449192082 | `71c547b02982fe3b090977c100437d6741f7ef645eb9fc08785c947ace63c2a0` |
| Portable ZIP | 99390057 | `015bc799f9c592ec739faf431d09cf9eb16ce771087ce2df544dec022c38927f` |

The existing publisher verified both remote staged artifacts and atomically
switched `agent-current` to `agent-releases/2026.10.6.1`, retaining
`agent-previous` at **2026.10.2.3**. Public metadata matched the tested manifest.
Both files were fully downloaded through public HTTPS URLs from the VPS and
matched the sizes/hashes above. Full operator-PC download timed out; its 1 MiB
installer range was downloaded with curl and matched the local file exactly.

Local ignored evidence is under `build/qa/release-20261007/`: source/build
inputs, build logs, installer lifecycle log, tested manifest, production
deployment/backup logs, publication log and complete VPS HTTPS verification.
The final artifact manifest is authoritative.

## Limits

Live throughput and sustained provider limits have not been measured. No claim
of 0.5 answers/second is established. Multi-account support was not added.
Existing resumed scans retain their frozen legacy timing settings. CAPTCHA and
confirmed quota still stop browser admission. Manifests/binaries remain unsigned;
HTTPS and hashes provide the existing integrity checks. Real power loss,
older-installation upgrades and WebView2 click-to-relaunch remain open.
