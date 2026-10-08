# Shared frontend rules

Read root `AGENTS.md`; read `PRODUCT.md` and `DESIGN.md` for UI changes.

- React/TypeScript + Vite, existing components/styles; retain Russian copy, dark violet
  palette, keyboard access, labelled controls, focus and reduced motion. Use native
  controls or installed components before dependencies. Do not edit vendored React Bits
  merely to match formatting; preserve licenses.
- Website configures projects; agent executes scans. Local `/api` and server `/api/v1`
  are different contracts (`lib/api.ts`, `account-api.ts`, Vite proxies). Trace the actual
  endpoint and server response before changing types or optimistic UI state.
- Polling must not overwrite dirty forms. Preserve revision conflicts, loading/error/
  empty/offline states and late-response handling when switching projects/results.
- Client visibility is not authorization. Server must enforce owner/admin/device access.
  Never embed secrets or model/provider credentials in JS or Vite variables.
- Edit source in `frontend/`, then build and include generated `web/` changes. Do not
  hand-edit hashed assets or rebuild unrelated frontend during a backend/docs-only task.

## Checks (run inside `frontend/`)

If dependencies are missing, `npm ci` with the existing lockfile (CI uses Node 24).
Then `npm test`, `npm run lint`, `npm run build`. A focused Vitest invocation may be
used while iterating; final frontend gates run once after the last source change.
For changed user flows also smoke-test using disposable data: exercise success/failure,
one desktop and one narrow viewport; check console and keyboard behavior. Use
`scripts/frontend_smoke_server.py` only after reading its setup; real sessions are not
fixtures. Report an unavailable browser check explicitly instead of claiming it passed.
