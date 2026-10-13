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
self-check passed.
Full server passed241 before the final capacity fix. Sol review found a sticky
full-capacity pause; its SQLite/PostgreSQL regression failed with the old pause
and passed with capacity refreshed after slot release. Sol re-review and Astra
risk review passed. Final full server passed243 with disposable PostgreSQL.
PR56 merged as67575132d4f4d3b0852fc9c62bd7e5fdbb2f8aab after exact-head
CI38384826583 passed on1bf2344a29cb37fca0b69a51afe4de4c80d7a82d.
Production CI38385385962 passed, including backup/isolated restore and readiness
gates. HTTPS readiness and remote production both match67575132; pricing120.
Live read-only acceptance: geosoft-dent ChatGPT121 ->301/303 and Yandex186 ->203/303.
One pre-existing uncertain task remains isolated, never reposted; one expired
handle and Yandex tail remain for normal recovery. No paid QA scan/history rewrite.
Disposable PostgreSQL55433 stopped; VNC diagnostic transaction closed and fit
scale restored. No new SSH access was created.
No migration, frontend or delivery-script change.
