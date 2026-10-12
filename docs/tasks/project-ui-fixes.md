# Project UI fixes — 2026-10-12

Outcome: sparse visibility measurements stay readable; standalone Alice is absent
from website reports, exports, project marks and the private scan list. Current GPT
and Perplexity SVG colors load even with old browser caches. Project views show the
active check's progress; automatic server retries say «В процессе», explicit pauses
stay paused. Project list/sidebar icons use the first brand domain's favicon.

Base: codex/chart-gaps from production 2c50130; no pre-existing user changes.
Scope: report chart/view, shared service marks, ControlCenter, project icon,
legacy agent service choices, admin scan list/SQL filter and generated web assets.
Keep: historical answers and detail APIs, owner/admin scopes, totals before
pagination, saved current report selections, real zero/missing measurements,
true pauses/stops, dirty forms and durable execution/billing contracts.

Acceptance: unit regressions for sparse lines/actual markers, retired choices and
mixed saved choices; server list excludes Alice before count/pagination without
deleting detail evidence. Run status regressions cover retry/user pause/stop/done;
progress exposes native labelled counters. First-domain favicon supports bare and
IDN domains, invalid/absent/broken icons fall back without layout shifts, and a
changed project/domain can load a new image after a failure.

Checks: full server (184 passed including disposable PostgreSQL), final frontend
test/lint/build, disposable desktop/narrow browser success/failure/keyboard/console,
independent Sol review and Astra release risk review, diff check.
Publication is already authorized. Feature PR targets main, release PR production;
exact-SHA CI/deploy/readiness and asset byte equality are required before completion.
No migration/config/price change. No paid provider, payment or S3 request needed.

Evidence: 184 server tests (including five PostgreSQL) passed, 74 frontend tests,
lint exit 0 with warnings and build passed. Desktop/narrow browser covered progress,
true pause/retry/history filter, hidden Alice, actual marks, favicon failure and
new-domain recovery; no console errors/warnings captured. Both screenshot-site root
favicons returned 200. Downloaded XLSX must contain the same current service subset
as the displayed report (regression caught extra blank Gemini columns before fix).
No-current-services exports are disabled rather than issuing an invalid request.
All active runs remain visible alongside 100 recent finished runs (103-row regression).
Sol/Astra findings fixed and rechecked. Published through feature PR #45 and release
PR #46: production 488d5f3baa9fcb8d42897f4e8ab39e40700cc7f3, CI/deploy run
38248217391 succeeded. Public readiness matched the production SHA; 11 referenced
assets matched the tested web tree; anonymous private routes returned 401. Public
home/cabinet loaded the new bundles without console errors/warnings; versioned
GPT/Perplexity icons loaded. Evidence:
C:/codex-tmp/airate-project-fixes-release-20261012/.
Authenticated project acceptance used disposable fixtures, not production data.
