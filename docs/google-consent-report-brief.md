# Google consent and dated report results

User request (2026-10-02): accept Google cookies automatically so searches can run; display **Не проверялось** when a service was not checked on a selected date, without presenting an older result as current.

Status: website/API revision `556dc031e17a384ac4d6914b0a187e0af45c7644` is deployed through PR #23; readiness, production CI and actual backup/isolated-restore logs passed. Windows **2026.10.2.2** is built and its isolated installation, bundled-browser self-test, same-version reinstall and data-preserving uninstall passed. Windows **2026.10.2.2** is published; complete installer/ZIP hashes and sizes match via public HTTPS from the VPS, and **2026.10.2.1** is retained for rollback. Live consent-banner verification remains pending. Evidence: ignored `build/qa/google-fix-final-20261002-160857`.

Final validation: Google 14, overview 23, local exports 7, server reports 5 and frontend 50 tests passed; scan benchmark self-check, lint and tracked-web build passed. A fixed UTC-clock regression removes a test-only midnight ambiguity. Independent Sol/Astra reviews found no remaining actionable findings. Isolated browser QA retained the old September 26 GPT login error in the historical period, then showed only three **Не проверялось** cells and zero result buttons for GPT on October 2. Proof: ignored `build/qa/google-fix-ui-proof.json`, `google-fix-gpt-table.jpg`.

Operational evidence: Geosoft run on WEB-PM ЕГОР selected Google/Alice. Google input was covered by its cookies dialog, causing three blocked-input failures and 300 skipped rows. Geosoft GPT has 303 historical auth-required results on 2026-09-26; the current agent reports a saved GPT session, but today's run did not include GPT. Ignored diagnostic evidence: `build/qa/geosoft-server-check.jsonl`, `geosoft-gpt-check.jsonl`.

Inspection found cells are already keyed by query/service/date. The defects are missing Google consent handling, default/preset periods anchored to the last saved date, service-filtered date columns, and local custom-date selection discarding dates without scans. Preserve historical results; do not rewrite them from current session state.

Scope: Google-only consent handling using existing navigation/click helpers, shared by readiness, query navigation and recovery; exact visible Russian/English accept button, dismissal before typing, CAPTCHA behavior retained. Central report defaults/presets end today; date columns are independent of result filters and include selected endpoints. Local overview retains explicit empty dates and range endpoints. Missing cells, labels and exports say **Не проверялось**, remain non-clickable and contribute no successful/error counts. No migration, deletion, charging change, generic consent framework or shared quota/retry reclassification. Native version **2026.10.2.2** retains the configured public Sentry DSN.

Explicit empty boundaries apply to period and two-date comparison only; monthly keeps each month’s latest actual measurement, and custom keeps its picked dates.

Acceptance: old GPT auth-required results remain only on their historical date; a GPT-only current-date view has no older result IDs and shows unchecked cells. JSON, UI, comparison and XLSX agree, including explicit empty dates. Google handles Russian/English banners, repeated recovery and no-banner pages; hidden/unrelated controls are untouched and an undismissed dialog cannot allow query typing. Use existing Google, reporting, overview and calendar suites plus frontend lint/build, independent correctness/risk review and post-deployment checks.

Limitations: the current inspected Google browser profile has no consent banner, so actual consent dismissal in the Windows agent requires later live confirmation. This change does not repair historical failed scan results or stop the ongoing Geosoft run.

The report UI sends its local calendar day as `date_to`; direct API clients that omit it retain the server UTC default.

Native evidence: ignored `build/qa/google-fix-native-source.json`, `google-fix-portable-proof.json`, `google-fix-installed-lifecycle.log`, `google-fix-installed-runtime.json`. Checks cover an isolated same-version reinstall, not an upgrade from a real older user installation.

Final publication evidence: ignored `build/qa/google-fix-release-evidence.json`, `google-fix-public-artifacts-vps.json`, `google-fix-publication.log`. Installer: 469,993,766 bytes, SHA-256 `6828682b02100193da89ab7ad87ab5160a5f391fa03a55872fd78a0722667920`; portable: 121,113,130 bytes, SHA-256 `5528d95120da8007eb1fffa3f354e65311bd9c696f0355463e8bb894e96dcfb6`.
