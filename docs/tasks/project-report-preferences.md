# Project report preferences — 2026-10-12

Scope: current project configuration limits chart/report/filter/export systems;
homepage uses the Gemini logo; calendar range persists after browser reopening.
Keep stored history, owner scopes, saved valid subset, dates and export alignment.
Reuse current report selection, localStorage pattern and existing Gemini asset.

77 frontend tests passed; lint exit 0 with warnings and TypeScript/Vite build.
Regressions failed before configured-choice filtering and Gemini logo correction.
Stored range tests cover valid/leap dates, malformed/nonexistent/reversed dates and
the report period limit. Sol read-only review found no blocking defect.
Disposable browser checked two-system legend/stats, removal of a saved choice via
settings, reopening the selected calendar range in a new tab, another project's
default range and Gemini legend, keyboard and mobile no-overflow/console checks.
Project settings prevent saving an empty service selection. Date storage is local
to this browser and disappears when its site data is cleared; unavailable storage
does not prevent using reports. Evidence: C:/codex-tmp/airate-project-services-20261012/.

Published through PRs #47/#48: c7e6c2736ca8c649407bd875a182236eddef6106.
CI/deploy run 38261782655 succeeded, public readiness matched that SHA, all 11
fetched assets matched the tested tree and anonymous private routes returned 401.
Public homepage Gemini logo loaded; cabinet serves cabinet-C0HK4bK9.js.
Backend and provider integrations are unchanged; no paid requests/payment/S3 check.
