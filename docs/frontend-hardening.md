# Frontend draft and evidence fixes

## Scope

Fix three browser-reproduced defects in the cabinet. Base: `ac84a05`.
No visual redesign, backend changes, payment changes, real scans or EXE rebuild.

1. A project draft disappears without confirmation through Account, logout and hash history navigation.
2. A successful delayed save replaces edits made while the request was pending.
3. A delayed screenshot for answer A appears in the dialog for answer B (or its failure appears under B).

## Minimal solution and objection

Guard actual editor departure consistently, freeze mutation controls during save using native disabled controls, and reuse the result request generation for screenshots. The strongest objection: freezing fields slows editing on a slow network. Accept this bounded tradeoff instead of adding draft merging and revision conflict handling on the frontend.

## Acceptance and regression checks

- Dirty Account, logout, project/report navigation and browser Back/Forward ask once; cancelling retains the exact draft and route, confirming leaves. Clean navigation asks nothing.
- Queries/settings within the same project preserve the draft without asking.
- Native unload protection remains. New-project save redirects to its created project without a false dirty warning.
- Pending saves disable every mutation path, including query import dialog, group edits, deletion and month-day buttons. Failure retains the draft, displays the error, unlocks controls and permits retry.
- Existing-project and new-project saves work; an older response must not update a different mounted editor.
- Late screenshot success/failure does not affect another answer or a closed/reopened dialog. Current screenshot still loads.
- Existing report filters, calendar, query import, auth/logout and account/topup navigation keep working. No whole-page overflow at 390px and normal desktop width.

## Checks

Existing Vitest suite, oxlint and TypeScript/Vite build; browser scenarios with deliberately held/failed save and screenshot requests on an isolated loopback fixture. Leave a reproducible fixture and manual scenario, using existing dependencies. Independent Sol review of the final diff; Astra risk review for draft loss and logout transition. Review repairs rerun affected checks. No empty checks reported as passing.

## Baseline evidence

2026-09-29, loopback fixture port 8793 and disposable SQLite database:

- Changed project name; Account then Workspace: no dialog, original name restored.
- Held PUT, changed name after Save, released PUT: later name replaced by submitted name; status said saved.
- Held screenshot A, closed Google answer, opened ChatGPT answer, released A: `.report-shot` was `/__qa/shot-a.svg` under ChatGPT.

Final revision and verification results will be recorded after implementation.

## Reproduce locally

Build the frontend (`npm run build` in `frontend`), then run:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/frontend_smoke_server.py
```

The printed project ID belongs to a new temporary SQLite database. Open
`http://127.0.0.1:8793/cabinet/#/project/<project_id>/settings`.
This loopback fixture automatically uses a synthetic test account and clears inherited provider/database credentials; never expose it publicly. Stop with Ctrl+C.

Hold a request from a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8793/__qa/state -Method Post -ContentType application/json -Body '{"save":"hold"}'
```

Set `save` to `pass` or `fail` to release it. Likewise set `shot` to `hold`,
then `pass` or `fail`. `/__qa/state` also reports `seen` request kinds.

1. Change project name. Try Account, a different project view and browser Back. Cancel each confirmation and verify the draft. Repeat with confirmation accepted, then verify server values on return. Test logout last (it revokes the fixture session).
2. Hold save, Save, inspect disabled project/query mutation controls. Release with failure, verify retained draft and retry with success. Repeat in new project and verify its redirect.
3. In report open Google, 01.09.2026, first query (result A). Hold screenshot, click Open screenshot, close, open ChatGPT, 03.09.2026 (result B). Release A: no image/error should appear under B. Repeat with failure and with closing/reopening A. Request B's own screenshot: it should load.

## Final task 1 verification

2026-09-29: independent Sol and Astra reviews cleared the final repairs. Logged checks: `build/qa/frontend-hardening-20260929-02/report.json` (26 Vitest checks, lint, TypeScript/Vite, fixture syntax pass). Browser reproduced and verified held save controls, retained draft on 503 and successful retry, Account/logout cancellation, cancelled link followed by cancelled and accepted Back (accepted target remained Devices), forward navigation, import of 101 queries and multi-character rename of the last filtered row without losing focus, and late A screenshot ignored under B while B's own screenshot loads.

The fixture's visible QA checkbox deterministically accepts/dismisses `window.confirm`; counter shows prompts. Add `?native_dialogs=1` for native dialogs. Native confirmation visual behavior was not measured; IAB did not expose its dialog consistently. The viewport override did not change the measured width from 1280px, so 390px mobile is not reported as verified. No real payments, scans, auth sessions or production data were used.
