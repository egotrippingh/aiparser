# Report history layout

Outcome: service toggles keep the report visible during refresh without a false
no-data notice. Icon/name buttons indicate selection. Query history shows every
actual scan date in the selected period, latest first, with compact service icons,
date dividers, left-side visibility/dynamics and horizontally sticky queries.
User explicitly requires continuous horizontal scrolling, without date paging.

Base: codex/promo-codes at0274ab3; promo/CSV changes already committed; clean tree.
Scope: ReportView, ReportChart, prototype styles/tests; compact overview daily
cells in reporting.py and regression tests. Preserve original matrix/XLSX contract,
owner/device authorization, latest-per-day retry, full-period totals and baseline.
One overview request carries only a visible date window of verdict cells; full
date scale scrolls continuously using spacers. No answer bodies added. Period
result filters use totals even if a matching cell is outside the loaded window.

Acceptance: >4 actual scan dates all present, no invented period boundaries;
latest retry wins; comparison still contains only endpoint cells; owner access,
bounded SQL and sources unchanged. Desktop/narrow browser verifies date order,
sticky query during horizontal scroll, immediate legend state, loading/error/empty,
keyboard and console. Run server suite, frontend test/lint/build and diff checks.

Additional outcome: manual false_positive/missed changes effective verdict,
all report totals, sources and XLSX immediately; original result/check/charges
stay intact. Existing max20 project feedback marks remain explicit in UI, undo
restores the current automated verdict; brand changes disable only learning.

Evidence: two history regressions failed before the backend fix (missing cells
and fabricated/paged dates). Manual-verdict regressions also failed before implementation. Final server suite:
279 passed with disposable PostgreSQL; frontend87/lint/build passed (existing lint
warnings). Sol high review found three P2 issues; all fixed and re-reviewed.
Astra high risk review was unavailable after two capacity failures; Sol covered
server money/data/migration risks. Browser verified false-positive changes924→923 mentions and removes checkmark;
missed mention/undo changes effective detail, keyboard Enter/Escape works.
Desktop1280 and narrow390 verified no page overflow,16px percentage inset,
calendar preset10px gaps, immediate gray legend with pending report/no false
banner, continuous28-date scroll to16.09 with query X unchanged249px.
Network error recovery remains an existing UI path, not re-exercised in this chunk.

Delivery: user authorized deployment of previous and current changes, including
the additive promo schema migration. Follow production PR, exact-SHA CI, database
backup/isolated restore and readiness gates. Disposable fixtures are never shipped. Production backup on2026-10-14 restored
successfully into an isolated DB. User subsequently requested persistent SSH;
dedicated local key and pinned host configured as alias airate-admin, verified
root login. Key forwarding is disabled; no credentials belong in Git.
