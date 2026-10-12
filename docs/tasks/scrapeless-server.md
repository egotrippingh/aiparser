# Server collection and administrator operations

Base: `b77f6fa`, clean `codex/xmlriver-streaming`; work on `codex/scrapeless-server`.

Outcome: new scans execute ChatGPT, Perplexity and Gemini on the server, alongside
Google AI Overview and Яндекс Поиск с Алисой. No user PC is required. Alice remains
in historical reports but cannot be selected for new work.

Keep: frozen run inputs/prices, owner scope, durable evidence before analysis,
once-only settlement, Stop/Pause semantics and legacy agent runs.

Acceptance:
- Server-only launch/schedules for five services; provider-specific configuration.
- Persistent submission intent and task ID; restart/GET errors never repeat POST.
- Shared account admission across users/workers; bounded reusable HTTP connections.
- Stop prevents new submissions and drains accepted results; late owners cannot bill.
- Markdown, tables, lists, safe links and brand highlighting remain readable.
- Admin-only paginated users/wallets and live supplier balances with cabinet links;
  unavailable values are explicit, Team Credits and subscription are separate.
- Fake-provider regressions, full server/UI gates, disposable PostgreSQL concurrency,
  reviewed additive migration and bounded live Scrapeless load verification.

Steps: durable supplier client/admission → runner/service contract → admin/UI →
checks and independent Sol/Astra reviews. One writer; planner/research are read-only.

Provider contract: official `/api/v2/scraper/request` and `/result/{task_id}`;
`shopping=false`; `country=US` is frozen separately from XMLRiver region.
Sources: https://docs.scrapeless.com/en/docs/ai-scraper/quickstart/task-lifecycle/

An ambiguous POST cannot be retried safely without supplier idempotency. Keep its
capacity occupied pending operator reconciliation. Never release it on run lease
expiry. Expired results remain unfinished for operator reconciliation, without a report row or another POST.

No production deployment, live migration, installer publication or push requested.
Secrets remain outside Git; transferred JSON is used only locally for authorised API.

Evidence on the final local tree (2026-10-12):
- `python -m pytest server -q`: 175 passed, including disposable PostgreSQL admission,
  fencing and owner fairness; additive migration upgrade/check passed SQLite/PostgreSQL.
- Client pipeline/billing/storage group: 52 passed; XMLRiver/detection group: 98 passed;
  agent sync/capture/plan/timing/session contract group: 33 passed; benchmark self-check passed.
- `npm test`: 61 passed; lint passed with warnings; production build passed.
- Disposable browser smoke: desktop and 390px; balances success/failure, cabinet links,
  all/no-scan users, search/empty state, keyboard table focus, five choices, Alice-only
  launch disabled, Markdown headings/table/list/brand highlight and literal HTML; no console errors.
- Live Scrapeless production client/runner, two synthetic owners: 100 ChatGPT + 100
  Perplexity + 100 Gemini POSTs, 300 saved/formatted responses, zero invalid report rows.
  Accepted unfinished peaks 100/100/89; configured cap 100 per actor. Elapsed 126.72/32.34/21.84s.
  Deterministic fake analysis; temporary PostgreSQL settled 300 checks and exactly 300 ledger debits.
- Sol correctness and Astra risk review: final targeted fixes have no remaining P1/P2.

Remaining release work: install Compose/env changes with SCRAPELESS_API_KEY and optional
OPENROUTER_MANAGEMENT_KEY; follow reviewed schema-head/backup/restore activation procedure.
No push/deploy/live migration/installer or live OpenRouter/XMLRiver balance call performed.
Ambiguous paid POST, expired answer and exhausted analysis budget require operator resolution.
External outages cannot guarantee an answer; unfinished work is never falsely reported as completed.
Secret-bearing evidence and synthetic answers remain outside Git.
