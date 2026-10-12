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
