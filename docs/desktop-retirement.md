# Desktop product retirement

AIRate uses the website and server for all new checks. The desktop product is retired; this release does not uninstall or modify an existing Windows installation.

## Website behavior

- The frontend build contains landing, cabinet, terms and privacy entries. The old desktop UI entry and its exclusive helpers are removed; no `web/app/index.html` or agent bundle is published.
- `/app`, `/app/` and nested old paths redirect permanently to `/cabinet/`. Supplied destinations do not change the redirect target.
- `/api/v1/agent-download` keeps its response shape but always reports `available: false`, with no URL, size or release.
- Both old EXE/ZIP download endpoints return HTTP 410 even if a retained artifact exists. Files on disk are not deleted.
- Landing content and result guidance describe server collection. They do not ask users to install software, sign in through an agent or solve a captcha on their PC.

## Compatibility boundary

Account data, results, device records, billing recovery and historical upload/control protocols remain intact. Previously installed applications can still send compatible state and old job results; privacy text explicitly covers this processing. The server imports shared detection helpers from `app/detect`, so deleting the complete `app/` tree would break server collection.

Existing Windows binaries retain their own bundled UI and local data. Their old update checker treats a missing release as unavailable/error; it will no longer offer a download. This website-only retirement does not ship a binary update to change that old message. New Windows builds and source desktop launches are retired and are not supported by the website build. The historical packaging/runtime files are not a second supported product.

## Verification and delivery

Regression checks cover fixed redirects, unavailable metadata, HTTP 410 with existing artifacts, preservation of those artifacts, and server-only landing/error guidance. Run frontend tests/lint/build, affected server tests and full delivery CI. Verify absence of the desktop entry after building. Smoke-test the redirect, homepage and cabinet on disposable state at desktop and narrow widths.

Deliver through a feature PR into `production`, preserving existing backup restore, schema-head, exact-release readiness and rollback gates. Check live redirects, download retirement and generated frontend assets after activation. Runtime evidence belongs in the PR or ignored `build/retire-agent-20261016/`.
