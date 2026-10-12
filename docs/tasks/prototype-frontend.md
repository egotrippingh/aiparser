# Prototype frontend

Base: 2452147, clean checkout; branch codex/prototype-frontend.
Reference: supplied airate-prototype-2026-10-12.zip (visual and interaction reference).

Outcome: account app matches the supplied white/navy/orange prototype;
website has no agent/download/computer navigation. Homepage retains its blocks
and copy, with the new palette and shared logo.

Scope: Brand/theme, cabinet, ControlCenter/ProjectEditor, ReportView/QueryLibrary,
owner-scoped aggregate report data, tests, generated web assets.
Keep: authentication, admin access, billing, revision conflicts, dirty-form guards,
safe answer formatting, historical results, exports and server collection.

Acceptance: nine prototype sections with real data and loading/empty/failure states;
continuous grouped report; equal-length previous period and selected-date comparison;
safe source links; keyboard/mobile/late-response checks; npm test/lint/build,
server suite, independent review and git diff --check.

Steps: shell/assets; management/account; report contract and presentation; gates.
Publication: local commit only; no push, migration or deployment authorized.

Completed 2026-10-12: nine real-data sections, shared prototype logo/palette/service
marks, grouped report with compact owner-scoped data, chart keyboard/crosshair,
equal-calendar comparisons, domain source counts and matching filtered XLSX.
Missing measurements remain gaps; a domain is counted once per answer. Homepage
blocks/copy remain, with palette/logo and removal of the agent download link.

The user explicitly retired the website agent: legacy `connect/provider` URLs
now open ordinary account login without authorizing a computer. Re-login from an
old desktop agent through those URLs is intentionally discontinued. Historical
results and server execution APIs were retained; no installer was published.

Final checks: 67 frontend tests / 12 files, lint exit 0 (including new warnings),
TypeScript/Vite build; 178 server tests passed, five disposable-PostgreSQL checks
skipped because AIRATE_TEST_POSTGRES_URL was unset. Integration-release PostgreSQL
and live-provider evidence is recorded separately in scrapeless-server.md.
New regressions for isolated chart points and source-export mode failed before
their fixes and passed afterward. Sol/Astra independently reviewed the changes;
no unresolved defect remains in the requested server-only website flow.

Loopback-only disposable browser fixture: 1440x950 and 390x844; no page overflow,
keyboard chart/choices/skip link, empty data, duplicate import, dirty cancellation,
save/report failure and recovery, held responses, answer formatting and safe links,
filtered source XLSX, project selection, separate search and retained date/mode,
wallet refresh, FAQ and ordinary login through legacy URLs. Login sent only email
and password; fixture developer console had no errors/warnings. Screenshots and
private QA evidence: C:/codex-tmp/airate-prototype-qa/ (excluded from Git).

Limits: no authenticated production browser scan, live payment, S3 or installer
check for this redesign. No frontend publication was performed.
