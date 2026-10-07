# Scan throughput delivery — 2026.10.7.1

Scope: [checked brief](scan-throughput-brief.md). Base production source:
`791dccbb2f93379a0557e0c4571af4950da74d3c`. Published through
[PR #28](https://github.com/egotrippingh/aiparser/pull/28), source
`fba1f8466457666f04ded8cc180ae3a25cf64276`.
[Production CI/deployment](https://github.com/egotrippingh/aiparser/actions/runs/37602006061)
passed. Backend activation preceded the Windows release.

## Shipped defaults

- One durable screenshot-outbox consumer runs independently of analysis and
  managed-run polling. Conditional acknowledgements protect replaced queue
  entries, failed files retry without killing the worker, and batches advance
  in queue order. Each batch pins the actual authenticated account token.
- Agent HTTP requests share an asynchronous client; local model requests share
  a synchronous client. Lifespan shutdown drains/cancels tracked work before
  closing clients. Capture planning selects metadata without screenshot BLOBs.
- Phase timings expose browser capture, analyzer queue wait, analysis and
  settlement. The historical result duration is not an end-to-end scan time.
- ChatGPT/Perplexity settling checks compare the full text; timeout rejects a
  partial answer. Existing adaptive provider floors and legacy timing snapshots
  remain intact. Provider parallelism already exists; no user configuration was
  changed automatically.
- A saved answer can explicitly continue its original check with a lifetime
  maximum of four primary/four arbiter attempts (normal budget: two each).
  Reservations cannot reset those counters. No new browser answer is required.
- Native desktop abandonment retains raw evidence and an error report, releases
  unanalysed checks, settles cached primary analysis once, and durably retries
  the managed terminal report. Resume paths cannot resurrect abandoned captures.
  Transient prior results receive a fresh error ID so an advanced sync cursor
  still sends the operator's decision and retained evidence.
- Scan admission, token replacement and tracked background work share the
  account-change guard. The device/run status endpoint validates both owner and
  assigned device; abandoned work cannot be reported against a foreign run.

## Measurements and limits

Private reproducible evidence is in ignored
`build/qa/throughput-20261007/`; provider profiles and debug captures are not
published. Measurements below are observations, not sustained throughput claims.

| Check | Observed result | Limit |
|---|---|---|
| 20 local HTTP/1.1 requests | Base: 20 TCP connections / 4.412 s; candidate: 1 / 0.168 s | Direct loopback, candidate excludes initial shared-client creation; not provider latency |
| 24 synthetic answers, three interleaved rounds | Final median: one analyzer 4.456 s; two 3.397 s (~24% faster) | 0.02 s capture / 0.10 s mocked analysis; no paid/provider calls; earlier run ~34%, PC load varies |
| Google, two same-query copied-profile trials | Base asks 17.640 / 27.156 s; experimental 16.250 / 17.328 s; typing ~0.063 s | Small sample, generated content differs; image completeness not qualified |
| Alice copied-profile trials | Base short answer completed; long answer timed out; candidate required login | No reliable paired speed comparison |
| ChatGPT copied-profile trials | Session unavailable | No live throughput qualification |
| Existing parallel mode / memory | Installed project enabled; developer projects disabled. Two browsers ~1.78 GB on a 15.8 GB PC in one observation | Other applications consumed memory; not a universal minimum or permission to increase concurrency |

Two analyzers remain an opt-in local developer setting, frozen in each scan;
configured client agents have no switch. Direct fill, skipping preparation scroll
and Google DOM readiness are explicit benchmark flags only. Default Google
navigation/screenshot code is unchanged. Live image probes included truncated
text or repeated sticky content, so these experiments were not promoted.
Neither these trials nor synthetic overlap establish 0.5 answers/second.

## Verification

- Independent Sol correctness and Astra payment/auth reviews covered the final
  code. The account-rotation defect was reproduced with 101 pending reports
  before repair; a blocked tracked-sync regression now prevents remote exchange
  or owner changes and keeps both report batches under the original bearer.
- Actual local agent and server handlers verified abandonment: absent primary
  analysis leaves a 10000-kopek wallet unchanged; cached primary leaves 9880.
  Repeating abandonment and terminal delivery does not charge again. Evidence
  remains; the terminal marker disappears only after acknowledgement.
- Actual native `/app/` fixture verified the accessible confirmation, Escape,
  focus return and completed action. No real account or paid provider was used.
- The full server suite passed locally: 74 tests. Final checks: pipeline and
  abandonment 31; HTTP/files/settling 10; compatibility 107 (two platform skips);
  provider timing 22; parallel mode 11; frontend 50. Benchmark self-check,
  compile, diff check and frontend build passed. `final-checks-v2` records one
  failed wall-time ratio during concurrent synthetic/AST work; unchanged-code
  isolated parallel rerun passed (`parallel-isolated.log`). The overlap and
  result-integrity assertions passed in both runs. Exact-head GitHub CI is
  passed before merge and again on production. Linux CI ran the two Windows-skipped
  checks successfully (109 compatibility tests). EXE self-test and bundled-browser
  startup passed. Isolated installer verification compared all 1819 source files,
  launched the installed EXE/browser, reinstalled the same version, and uninstalled
  while preserving both current and legacy data sentinels. This was not an upgrade
  from an older real installation.

## Published artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| [Installer](https://airate.tech/downloads/AIRate-Setup.exe) | 449214915 | `d2541147a95edd664df7358485530f847ca790639e29df319deff8b41e809c3f` |
| [Portable](https://airate.tech/downloads/AI-Mentions-Windows.zip) | 99401479 | `0b352f4763804470ee7edeb21c47e9d310cf804907f114bb16b408f5c91521e6` |

Publishing verified staged sizes/hashes before atomically switching the release
pointer. Public metadata matches version 2026.10.7.1 and the local manifest.
Both complete HTTPS downloads/hashes passed from the VPS; the operator PC checked
readiness, pricing, metadata and the installer first 1 MiB against the local file.
This does not prove complete downloads from every network. `agent-previous`
retains 2026.10.6.1. Private evidence: `public-final.json`, `installer-test.log`,
`build-exe.log`, `publish-agent.log` and `production-ci.log`.

Readiness verified production source `fba1f8466457666f04ded8cc180ae3a25cf64276`;
price remained 120 kopeks. Deployment saved
`backups/aiparser-20261007T094120Z-2099139.dump` and restored it successfully into
an isolated database before activation. That backup remains on this VPS.

## Recovery

After abandonment, the minimum compatible desktop version is **2026.10.7.1**.
Older agents can resurrect abandoned capture rows. A recovery release must be
forward-versioned and retain abandoned-state filters, settlement identities and
the durable terminal marker. Do not restore a pre-abandonment client database
against already settled server checks. Previous downloads are retained for
recovery evidence; they are not a safe downgrade for that database.

Backend rollout precedes the agent: saved retries and the owner/device run-status
endpoint require this backend. No schema migration is introduced. Preserve the
server's backup/isolated-restore/readiness gates; do not roll back to a backend
without those routes while clients are using them.

Open checks: sustained real-provider throttling, real-profile power-loss recovery,
an upgrade from an older installed agent, existing-user WebView2/tray/logon,
PostgreSQL concurrency and a separate off-VPS database backup. Installer signing
remains unavailable. Deployment procedure: [delivery](../deploy/DELIVERY.md).
