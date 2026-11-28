# Shared frontend rules

Read root `AGENTS.md`; read `PRODUCT.md` and `DESIGN.md` for UI changes.
The dark design uses the shared SCSS in `src/styles/`. The desktop design
reference is the approved preview under `design-system/`.

## Design system and SCSS

- Keep authored website styles in SCSS. Use Sass modules with `@use` and
  `@forward` for shared tokens, mixins and component styles.
- Define palette, typography, spacing, radii and motion tokens once. Consume
  the same tokens and component styles in the site, cabinet and preview.
- Use BEM for new blocks, elements and variants (`block`, `block__element`,
  `block--modifier`). When updating legacy markup, migrate its CSS and markup
  together. Reuse shared button, form, table, dialog and loading states.
- Verify desktop and narrow layouts, keyboard focus, hover, reduced motion,
  loading, empty and error states. Keep generated and vendor CSS intact.

- Reuse `AppChoice` for cabinet dropdown menus, including calendar modes and limits;
  use its shared popup, option and selected states rather than browser-native select menus.
  Keep toolbar buttons and dropdown triggers rounded (9 px), aligned and equally tall
  (32 px on desktop and 36 px on touch screens). Icon-only actions must match adjacent controls.
  Pointer clicks must not add bright outlines or focus glows; preserve subtle visible
  keyboard focus, accessible labels and arrow-key/Escape operation. Check the actual
  row and open menu in the browser after changing controls.

- React/TypeScript + Vite, existing components/styles; retain Russian copy, the approved
  graphite/lavender palette, keyboard access, labelled controls, focus and reduced motion. Use native
  controls or installed components before dependencies. Do not edit vendored React Bits
  merely to match formatting; preserve licenses.
- Website configures projects; server executes all five new service choices.
  Historical frozen agent runs retain their execution. Local `/api` and server `/api/v1`
  are different contracts (`lib/api.ts`, `account-api.ts`, Vite proxies). Trace the actual
  endpoint and server response before changing types or optimistic UI state.
- Polling must not overwrite dirty forms. Preserve revision conflicts, loading/error/
  empty/offline states and late-response handling when switching projects/results.
- Client visibility is not authorization. Server must enforce owner/admin/device access.
  Never embed secrets or model/provider credentials in JS or Vite variables.
- Edit source in `frontend/`, then build and include generated `web/` changes. Do not
  hand-edit hashed assets or rebuild unrelated frontend during a backend/docs-only task.

## TypeScript

- Prefer existing types next to `lib/api.ts` / `account-api.ts`; pin server error shapes
  in tests instead of inventing parallel DTOs.
- Do not claim UI authorization; hide controls for UX only. Access is enforced on server.
- Avoid `any` on changed public boundaries; narrow with existing unions or response
  parsers. Do not add `useMemo`/`useCallback` by default unless the file already does.
- Russian user-facing copy only; no supplier/model names for ordinary users
  (`PRODUCT.md` anti-references).
- State transitions stay explicit: pending, error, offline, empty. Polling updates must
  not clobber dirty form fields or lose revision conflict signals.
- After `frontend/` source edits, run build so tracked `web/` stays in sync; never
  hand-edit hashed `web/assets/*`.

## Checks (run inside `frontend/`)

If dependencies are missing, `npm ci` with the existing lockfile (CI uses Node 24).
Then `npm test`, `npm run lint`, `npm run build`. A focused Vitest invocation may be
used while iterating; final frontend gates run once after the last source change.
For changed user flows also smoke-test using disposable data: exercise success/failure,
one desktop and one narrow viewport; check console and keyboard behavior. Use
`scripts/frontend_smoke_server.py` only after reading its setup; real sessions are not
fixtures. Report an unavailable browser check explicitly instead of claiming it passed.
