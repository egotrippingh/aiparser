# Automatic recovery of new collection tasks

Outcome: new cloud checks recover after transient collection failures, including
empty terminal Scrapeless answers and more than three failed tasks. Old completed
results/runs remain unchanged, per user clarification on 2026-10-13.
Base: production 99d7fb34584eb9b12dab1378d7b73960fe4a86a5 plus local release-evidence docs.
Scope: collector/task admission/stream queue; report source filters and switches,
shared exports, regression tests and generated cabinet assets.
Keep: owner scope, account admission locks, run leases, provider pauses, stop/pause,
saved accepted task IDs, durable capture, one wallet settlement and original history.

Findings: XMLRiver already sends ai=1, retries API 500/empty content with one shared
six-request budget and defers new complete-policy runs instead of publishing errors.
Its documented empty content can mean only block presence was requested; no new
parser failure is established. Screenshots show historical results from 4/9 October.
Scrapeless success with empty text leaves the same task submitted; three rejected
tasks permanently block subsequent admission despite automatic run retries.

Acceptance: empty completed task becomes retryable without an error report; known
failed tasks recover after a durable cooldown beyond three attempts; no early resend,
duplicate settlement, restart duplication, legacy change or ambiguous POST resend.
Known expired task: re-GET after 15 minutes; preserve a recovered answer or retry
only that task if still terminal. Provider may charge again; user settles one Check.
Other same-service queries use free capacity; full account/unknown submission/global
quota yields that service on this pass, while healthy services drain. Admission wait
is bounded, so an external owner's occupied slot cannot retain the run indefinitely.
External-source switch off counts only found answers with safe HTTP(S) sources on
configured brand domains/subdomains. Card filtering remains independent. Keep
original answers/statuses, checked denominator, graph/table/trends/XLSX consistency.
Use disposable SQLite/PostgreSQL, fake providers; never change production history.
Steps: failing regressions; bounded recovery; server gates and independent reviews;
authorized release and exact-SHA public verification.
Evidence: pre-fix empty terminal/>3 attempts failed; queue regression failed 2 vs3
successful pairs before unblocking. First full server suite with disposable PG:
216 passed. After independent review fixes: Scrapeless suite 52 passed with PG,
including global quota/occupied slot, free capacity, late expired answer/new-owner
CAS and one wallet settlement. Focused reports/recovery 20 passed; frontend84
passed, lint0 errors(existing warnings), build passed. Browser disposable data:
keyboard switches; metrics75→50 with cards off; desktop and390px viewport verified.
Independent Sol/Astra findings fixed and rechecked. Full server with disposable PG:
225 passed before the final cooldown fix. Four SQLite/PG cooldown regressions failed
before the fix; all four and the strengthened third-query free-capacity regression
passed afterwards. Final full suite:229 passed with disposable PostgreSQL.
PR55 merged ddec8319283954deafe3b9d0d3e0691b84b4e539; PR CI38372134424
and production CI38372769409 succeeded. Normal public HTTPS verification confirmed
that exact release, pricing,12 matching assets and private endpoints401.
Live report switches are present; geosoft-dent advanced576→706/1212 after activation.
Complete-run finish is pending; no historical backfill or new paid QA scan initiated.
Evidence: C:/codex-tmp/airate-recheck-qa/. Temporary PG/report fixture stopped.
