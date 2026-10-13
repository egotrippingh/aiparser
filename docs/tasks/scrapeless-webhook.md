# Scrapeless callback and lost-submission recovery

Outcome: a lost POST confirmation recovers by callback or bounded timeout retry;
unknown tasks release capacity after the recovery timeout. One AIRate Check settles once.
User authorized implementation, recheck of the live uncertain geosoft-dent query,
tests and production deployment. Base22eda27; production67575132. Clean checkout.
Scope: ScrapelessClient.submit, provider_tasks admission/CAS/recovery, webhook
route and access-log redaction, existing cloud worker and fake-provider tests.
No schema or frontend change; delivery also validates the proxy configuration.
Callback contains check ID and a per-attempt capability; never log this URL.
Only persist matching upstream handle; retrieve evidence with authenticated GET.
Unknown/no-ID after15min can retry with fresh token/current active complete-run;
At most3 total submissions when confirmation stays unknown; preserve history,
then isolate for review. Other service slots and users continue normally.
Accepted task IDs remain GET-only. Pause/stop/auth/quota guards remain intact.
Known pending handles retain one occupied slot to avoid exceeding upstream capacity.
An upstream timeout retry can incur another Scrapeless charge; AIRate settles once.
Test wrong/stale token, wrong/malformed handle/body, duplicate/early callback,
callback vs POST failure/CAS/retry on PostgreSQL, timeout budget and no live owner
replacement, no second wallet charge, other user capacity, old history unchanged.
Steps: regression; minimal implementation; full server/shared gates and Sol/Astra
review; exact-head CI/deploy/backup/readiness; verify existing stuck query live.
Sources: docs.scrapeless.com/en/docs/ai-scraper/quickstart/task-lifecycle/ and
quickstart/ confirm webhook.url and task_id/status/task_result. Retention texts
disagree (4min vs12h); recovery timeout is application policy, not provider SLA.
Platform webhook guide describes Svix but AI request does not establish a signing
secret; callback body is notification only, never trusted answer evidence.
Evidence: new webhook regressions failed before implementation. Final focused19,
full server262 and shared67 pass with disposable PostgreSQL/fake providers.
Heartbeat test fixture mocks the new recovery function alongside recover_xml;
its heartbeat-delay assertion is unchanged. Sol/Astra findings fixed and rechecked:
POST/recovery lock, early callback vs Rejected/mismatched ID, invalid capability
before shared lock, and reverse-proxy URI redaction.
Caddy2.11.7 official binary/checksum: real upstream502 redacts the capability.
VPS Caddy2.11.4: original Caddyfile backed up, final filter validated and reloaded;
public HTTPS remained available. No scan data changed manually.
Live before release: geosoft-dent run desired running; one ChatGPT task uncertain,
attempt1, no handle; other ChatGPT tasks had completed. Yandex had a separate tail.
Delivery: source3a633685f6357e2b2a506ca0d2d77afb09fee145 passed CI38391368321;
PR https://github.com/egotrippingh/aiparser/pull/57 merged into production.
Production50f18ee979d980f450c9f458f4007bc1f72e626d passed CI38391886578,
including normal backup/restore/schema/readiness gates. Public HTTPS readiness
returns the exact release, pricing120; a fake invalid callback returns404.
Live read-only verification: queryd2f2e97ba0e3522bb838668f682fe51e in project
c9b4d8947a3340b3902bc9e6f9607cf4 automatically recovered on attempt2;
ProviderTask completed with handle, CloudResult has answer_text, one owner-scoped
Check settled. ChatGPT303/303, Google303/303, Perplexity303/303; Yandex278/303
with22 rejected and3 submitting tasks, still processing independently.
Actual upstream callback delivery was not forced; live automatic retry succeeded.
Provider fault scenarios used fake services; no old report history was rewritten.
The read-only DB connection was closed; browser viewport override reset.
