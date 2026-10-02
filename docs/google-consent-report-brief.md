# Google consent and dated report results

User request (2026-10-02): accept Google cookies automatically so searches can run; display **Не проверялось** when a service was not checked on a selected date, without presenting an older result as current.

Status: implementation and deterministic checks target Windows agent **2026.10.2.2**; publication and live consent-banner verification remain pending. Evidence: ignored `build/qa/google-fix-final-20261002-160857`.

Final validation: Google 14, overview 23, local exports 7, server reports 5 and frontend 50 tests passed; scan benchmark self-check, lint and tracked-web build passed. A fixed UTC-clock regression removes a test-only midnight ambiguity. Independent Sol/Astra reviews found no remaining actionable findings. Isolated browser QA retained the old September 26 GPT login error in the historical period, then showed only three **Не проверялось** cells and zero result buttons for GPT on October 2. Proof: ignored `build/qa/google-fix-ui-proof.json`, `google-fix-gpt-table.jpg`.

Operational evidence: Geosoft run on WEB-PM ЕГОР selected Google/Alice. Google input was covered by its cookies dialog, causing three blocked-input failures and 300 skipped rows. Geosoft GPT has 303 historical auth-required results on 2026-09-26; the current agent reports a saved GPT session, but today's run did not include GPT. Ignored diagnostic evidence: `build/qa/geosoft-server-check.jsonl`, `geosoft-gpt-check.jsonl`.

Inspection found cells are already keyed by query/service/date. The defects are missing Google consent handling, default/preset periods anchored to the last saved date, service-filtered date columns, and local custom-date selection discarding dates without scans. Preserve historical results; do not rewrite them from current session state.

Scope: Google-only consent handling using existing navigation/click helpers, shared by readiness, query navigation and recovery; exact visible Russian/English accept button, dismissal before typing, CAPTCHA behavior retained. Central report defaults/presets end today; date columns are independent of result filters and include selected endpoints. Local overview retains explicit empty dates and range endpoints. Missing cells, labels and exports say **Не проверялось**, remain non-clickable and contribute no successful/error counts. No migration, deletion, charging change, generic consent framework or shared quota/retry reclassification. Native version **2026.10.2.2** retains the configured public Sentry DSN.

Explicit empty boundaries apply to period and two-date comparison only; monthly keeps each month’s latest actual measurement, and custom keeps its picked dates.

Acceptance: old GPT auth-required results remain only on their historical date; a GPT-only current-date view has no older result IDs and shows unchecked cells. JSON, UI, comparison and XLSX agree, including explicit empty dates. Google handles Russian/English banners, repeated recovery and no-banner pages; hidden/unrelated controls are untouched and an undismissed dialog cannot allow query typing. Use existing Google, reporting, overview and calendar suites plus frontend lint/build, independent correctness/risk review and post-deployment checks.

Limitations: the current inspected Google browser profile has no consent banner, so actual consent dismissal in the Windows agent requires later live confirmation. This change does not repair historical failed scan results or stop the ongoing Geosoft run.

The report UI sends its local calendar day as `date_to`; direct API clients that omit it retain the server UTC default.
