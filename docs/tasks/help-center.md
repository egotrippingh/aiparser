# Public help center and shared header

- Outcome: replace the cabinet's short FAQ with a useful public Russian guide;
  restore shared header styling and use email support in the header.
- Base: `origin/production` at `8a37da3cc1b3f40947dd7587ed8f553ceab7f787`.
- Branch: `codex/help-center`; isolated managed worktree. The original checkout's
  unrelated uncommitted work is preserved.
- Synchronized with newer production `0a80911` (PR #67 workflow improvements);
  resolved only project-state documentation. Application files remained identical;
  21 release-status/delivery regression checks passed after synchronization.
- Authority: user approved the proposed content, public access, implementation and
  preview. Prepare a PR into `production`; publication is not yet authorized.

## Scope and acceptance

| Flow | Change | Acceptance |
| --- | --- | --- |
| Shared header | Isolate link colors/decorations from cabinet rules; mail icon and `mailto:support@airate.tech` | Guest and signed-in desktop/narrow views, hover/focus, dropdowns retain branding and navigation |
| Help entry | Shared Help links open public help; legacy cabinet help remains useful | Direct visit without session, cabinet entry and old link all reach documentation |
| Articles | Quick start, project/queries/import/groups, scans/providers/statuses, schedule/timezone, reports/answers/sources, billing/free scans, troubleshooting | Steps match actual controls and server behavior; examples work; no admin-only or provider-secret features exposed |
| Reading | Fumadocs where viable, existing AIRate brand/header, sidebar, section TOC, per-article/section links, mobile navigation | Direct URLs/reload/back/forward, no overflow at 320/390px, keyboard links and navigation |
| Search | Search article content in Russian, clear/reset and empty result | Matching body text finds article; unrelated text shows actionable empty state; keyboard works |
| SEO and copy | Dry task-based Russian text, natural search terminology, public HTML and metadata | Full text before JavaScript, one H1/canonical, sitemap contains eight articles; no invented keyword volumes |
| Support | Every article ends with email contact and useful incident details | `mailto:support@airate.tech`; no request for passwords/codes |
| Delivery | Frontend gates, affected server static route tests if needed, independent review, browser smoke | Record actual commands/results; generated `web/` included; PR into `production`, no merge/deploy |

## Verification, 2026-10-16

- Fumadocs 16.17.5 integrated with the existing Vite build and shared brand.
  Articles, static search and generated `web/` are included; no runtime SSR service.
- Final frontend: 115 tests passed; lint and production build passed. Lint retains
  existing warnings; CSS optimizer warns about Fumadocs `::highlight` selectors.
- Final `python -m pytest server/test_seo.py -q --durations=3`: 13 passed in 29.06s.
  Covers full public HTML, metadata, sitemap, search index, aliases and invalid paths.
- `python -m pytest server -q` exceeded the local 600-second cap without a reported
  test failure; this is incomplete, not a pass. Full CI remains a release gate.
- Browser, disposable loopback server on port 8873: guest legacy link opens help;
  full-text search, no-results/reset, Enter/Escape/Ctrl+K and focus return work;
  article links, reload/back/forward and section anchors work. No horizontal
  overflow at 320/390/800/1440px. Mobile article/TOC menus and signed-in support
  mailto in account menu verified. Section headings remain below sticky panels.
- Cabinet header: normal link colors, orange project action retained, logo hover
  has no underline; project filtering works. Dirty project → Help → cancel retains
  route and edited value. No real user data or paid scans used.
- Independent Sol source review and Astra risk review completed. Corrected exact
  button labels, narrow-screen support access, main landmark and search focus.
  No unresolved confirmed defects. `git diff --check` passed.
- Keys.so volumes were not available; terminology research and limits are recorded
  in [SEO policy](../seo.md). Existing npm audit findings are unchanged from base.
- Detailed local logs/screenshots are ignored under
  `graphify-out/qa/help-center-20261016/`; PR records the delivered revision/CI.

Next: review the interactive preview and PR checks. Publication is not authorized.
