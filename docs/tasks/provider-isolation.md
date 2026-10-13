# Provider queue isolation

Outcome: one uncertain/failed collection does not stop other queries or users
while account slots remain free. User authorized fix and production release.
Base: deployed PR55 ddec831; local clean bdaa92b includes release evidence.
Scope: _stream_run, provider_tasks.collect/collect_xml, XML transient network type.
Keep: ACTIVE account admission locks, accepted IDs, ambiguous POST never resent,
leases, provider pause/stop, global auth/quota/429 backoff and one Check settlement.
Live diagnosis: ChatGPT121/303 and one uncertain185min blocks service(limit100);
Yandex149/303 with75rejected,73attempts>=3,10 permitted slots. No analysis backlog.
Acceptance: existing/fresh uncertain leaves free slots usable without resend;
XML transient/timeout and Scrapeless400 don't set account-wide cooldown;
auth/quota/throttle keep global guards; per-query15min retry stays bounded.
Use SQLite and disposable PostgreSQL, fake providers, no history rewrite.
Steps: failing regression; minimal shared fix; full gates and Sol/Astra review;
production PR/CI and exact-SHA plus existing-scan live verification.
Evidence: before fix5 regressions failed (existing uncertain/submitting, fresh
ambiguous POST, XML transient and Scrapeless400). After fix96 focused provider/XML
tests passed including disposable PostgreSQL. Shared CI group67 passed; benchmark
self-check passed. Full server and independent reviews pending.
Full server passed241 before the final capacity fix. Sol review found a sticky
full-capacity pause; its SQLite/PostgreSQL regression failed with the old pause
and passed with capacity refreshed after slot release. Sol re-review and Astra
risk review passed. Final full-server rerun and production CI remain pending.
No migration, frontend or delivery-script change.
