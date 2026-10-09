# XMLRiver AI capture

## Outcome and base

- Request: collect Google/Yandex AI blocks through XMLRiver on a separate branch;
  retain existing answer analysis, reports and settlement.
- Branch: `codex/xmlriver-ai`; base `36066f50d66e0a193b86130b1ecb04a4be77b02d`.
- Base worktree clean; no release, push or production changes authorized.
- Use `google_aio` and the existing `yandex_neuro` SERP identity. Preserve `alice` chat.

## Scope and invariants

- Agent: configuration/secret references, adapter registry, XMLRiver adapter,
  provider snapshots/resume and readiness. Existing Capture/analysis contracts stay.
- Server/UI: enable existing Yandex SERP option and prevent unsupported old-agent jobs.
- Render a safe local representation for the existing screenshot/LLM pipeline;
  browser still required, provider login not required for API sources.
- Provider HTML must not execute scripts or fetch network resources; do not use
  real profiles/DBs/credentials in deterministic tests. Never log credential URLs.
- No change to detector/LLM/arbiter/deep-check semantics, pricing or migrations.
- API absence -> existing skipped; invalid/partial response retries automatically
  within the same three-request budget as HTTP/network/XML failures. Only
  exhausted/permanent failures become recoverable errors, never negative results.
- Preserve capture-before-analysis, stop/pause/cancel, outbox and once-only settlement.
- Freeze backend and nonsecret geographic settings. Old snapshots use browser Google.
- Project region is a Yandex code, not Google loc. Moscow mapping is verified;
  other Google locations require explicit matching configuration, no silent fallback.

## Acceptance

1. Fake Google/Yandex API responses become Capture with main/cards/plain/display,
   deduplicated sources and a valid image usable by the unchanged analyzer.
2. Hidden UI/query/source titles never become main recommendations. Yandex goods,
   prices and promo remain cards; Google source objects remain cards.
3. Empty/present-only AI, invalid XML/base64, HTTP/XML errors cannot become not_found;
   transient failures have bounded cancellable retries and timeout, no secret logs.
4. Resume preserves provider/geography; saved captures never trigger recollection.
5. Yandex can be selected in manual/scheduled UI; old agents cannot receive it.
   API readiness shows configuration separately from successful provider access.
6. Deterministic scoped agent checks, server suite and frontend test/lint/build pass;
   disposable browser smoke checks verify extraction/screenshots/UI if available.

## Work slices and evidence

1. Inspect flow and write brief: completed; Astra planner found caller/readiness gates.
2. One writer implements configuration, adapter and routing with regression checks.
3. Enable Yandex in server/UI with capability and backwards-compatibility checks.
4. Stop writing, run Sol correctness + Astra secret/data/settlement risk review.
5. Repair verified findings, final checks/diff, document setup and remaining limits.

Planner notes: API pilot 2026-10-08 had 6 successes/3 XML 500 failures, 0.21 RUB
total, Moscow. Those were data availability tests, not evidence of this integration.
Secrets and captures are outside Git; their contents must not enter this brief.
Builder routing: Terra unavailable in tools, use available Sol and disclose substitution.
No live model/payment tests, release or migration planned.

## Builder evidence (2026-10-09)

- Implemented API capture with opt-in environment credentials, frozen backend/geography,
  safe local HTML rendering and independent main/cards/source fields. Existing
  detector, billing and durable Capture contracts were left intact.
- Added Yandex choice to account preferences and managed project UI; server
  requires an explicit new-agent backend capability before creating or leasing
  Yandex jobs. API configuration and last successful request are separate states.
- Scoped checks after review repairs: `tests/test_scan_plan.py`,
  `tests/test_xmlriver.py` (including an offline Camoufox render and rule
  classification), and `tests/test_scan_pipeline.py`: 58 passed;
  `server/test_control.py` and `server/test_agent_dashboard.py`: 6 passed;
  focused frontend service-auth Vitest: 6 passed. Final evidence follows below.
- XMLRiver HTML screenshots are local representations, not native SERP images.
  Credentials and real provider answers remain outside Git. No provider,
  model, payment, PostgreSQL or production call was used by builder checks.

## Final delivery checks (2026-10-09)

- Sol/Astra re-review: all confirmed findings repaired; no remaining blockers.
- Root matrix: 322 Python tests passed; two existing Linux publication tests
  skipped on Windows. Frontend: 51 tests passed, lint/build passed. Benchmark
  self-check and `git diff --check` passed. Generated `web/` assets included.
- Reproducible command/exit/time/base-revision logs:
  `~/.codex/tmp/xmlriver-ai-20261009/checks-100338/report.json`.
- Offline fresh-browser fixture confirms organizations, source groups and goods
  remain cards; the unchanged detector returns `card`. No provider scripts or
  resource requests executed. Five saved real responses were also replayed.
- Final live neutral query through both adapters: Google/Yandex AI shown,
  valid JPEG, sources captured; zero render network requests and no credentials
  in INFO logs. No AIRate model call, payment or production database used.
- Disposable UI smoke: desktop and 390px width, keyboard Yandex selection,
  successful/failed saves, configured/unconfigured/successful/failed API state;
  no page or console errors and no horizontal overflow.
- Remaining limits: local representation instead of native SERP screenshot;
  Moscow verified, other Google locations require explicit matching configuration.
  No production deployment, installer qualification or real workload benchmark.

## Invalid-answer retry follow-up (2026-10-09)

- Base: local `5bc61e3`, clean tree. User requests automatic recollection of
  malformed XML and incomplete AI blocks before displaying a query error.
- One three-HTTP-request budget covers network/HTTP/XML errors and empty
  extracted main text. Backoff remains 1/2 seconds; valid absence, auth/quota,
  unsafe oversized/DTD payloads and saved-analysis behavior stay unchanged.
- Watchdog returns to ask phase before recollection; stop/cancel must prevent
  another provider request. Intermediate attempts must not write result rows.
- Regression on the unchanged implementation: 16 failed, 17 passed in
  `tests/test_xmlriver.py`, covering malformed/partial recovery and empty main.
- Acceptance includes mixed HTTP failure + cards-only block + valid/absent
  response, exhausted retries, identical query/geo, cancellation and stop,
  and no intermediate database result.
- Final scoped checks: XMLRiver/pipeline 62 passed; readiness/watchdog 46
  passed; pipeline/durable/billing/storage 52 passed (133 distinct tests).
  Benchmark self-check and diff check passed. Independent Sol review: no blockers.
- The first post-fix browser checks exposed a test fixture patching global
  asyncio.sleep and counting Playwright's own zero-delay waits. The fixture now
  replaces only the adapter's asyncio namespace; behavior assertions remain.
- Follow-up evidence summaries:
  `~/.codex/tmp/xmlriver-retries-20261009/report.json`.
  Fake providers and temporary databases only; no live provider/model/payment,
  production or installer check. After three failures the existing recoverable
  error remains visible; absolute absence of user-visible errors is not guaranteed.

## Production release (authorized 2026-10-09)

- User authorized production rollout to test XMLRiver and retries. The agent
  must be released as well as the website/API; target version `2026.10.9.1`.
- Current PC lacks local publisher credentials/build tools. Reuse the prepared
  Windows workflow/helper and pinned-host/public-verification publisher from
  `origin/codex/windows-agent-release`, without merging that unrelated PR.
- Add XMLRiver checks to delivery CI and the Windows release against the clean
  pinned browser. Dedicated production environment credentials are configured.
- Gates: feature CI, independent release risk review, production PR CI/deploy,
  Windows EXE/browser/install/upgrade/uninstall and atomic publish/full HTTPS
  checks. No production database migration or real user-profile test.
- Release progress and final SHAs/links will be recorded after verification.

### Scope changed before production merge

- PR #34 merged to main (`66c9086145d270360a0faa8954618efb18b429e6`);
  feature CI passed on `9f9d31b11d260e10e013a0fe7ab8e5c39c58fa47`.
  PR #35 into production remains open; no deploy or agent publication.
- User now requests text analysis without screenshots and HTML evidence display.
  Server-versus-agent execution was asked; user wants to inspect an HTML example
  before choosing. Hold production merge and Windows dispatch until scope resolved.
- Existing saved real API responses decoded into safe local Google/Yandex HTML
  examples for the same query. Preview/evidence outside Git:
  `~/.codex/tmp/xmlriver-html-preview-20261009/`; localhost port 8874. No new paid
  API calls, no screenshot generated, no external render requests or secrets.
