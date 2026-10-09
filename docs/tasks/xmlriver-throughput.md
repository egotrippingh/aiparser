# XMLRiver throughput and transient failures

- Outcome: use confirmed provider concurrency, save each returned answer before
  analysis, retry API 500/partial AI automatically within one bounded budget.
- Base: production `09df3b7`, equivalent source `d9c1687`; local `acd180d`
  contains release evidence only. Branch `codex/xmlriver-throughput`.
- Scope: shared XMLRiver collection/parser, server worker and existing tests.
  No migration, pricing change, installer or unrelated UI redesign.
- Source: `https://xmlriver.com/api/api-alt/`, `api/api-methods/`,
  `api/api-errors/`, `apidoc/api-about/`, `apiydoc/apiy-ai/`.
- Measured account limits: Google 10, Yandex 10. API AI collection is slower
  than ordinary SERP; low timeout can lose paid responses. Retain 90s timeout.
- Reproduction: two simultaneous Yandex requests from reported examples:
  API 500 after 40.62s; valid SERP without AI after 3.69s. Raw replies encrypted
  outside Git. Upstream absence/failure must not become a negative brand verdict.
- One writer: server builder owns cloud worker/tests; root owns shared collector,
  parser/tests/docs. Planner validated collection batches then sequential analysis.
- Keep: owner isolation, frozen inputs, stable check IDs, reserve before collection,
  durable capture before model, once-only settlement, pause/stop/resume and leases.
- Accept: up to confirmed 10 requests per engine overlap; each response persisted
  promptly; next batch waits for saved evidence; missing balance bounds reservations.
  Stop drains all saved/reserved work without new HTTP/model calls. Resume reuses
  captures. HTTP/XML/AI completeness share 6 server attempts, legacy retains 3.
  Empty first Yandex item with valid later content is analyzed; all-empty remains
  transient. Auth/balance/throttle do not get fast retry loops.
- Checks: regressions fail before fix; existing server suite/shared parser and
  affected client gates; benchmark self-check; independent correctness/risk review;
  exact-SHA CI and live smoke for authorized production correction.
- Limit: one application worker enforces account caps; multi-process execution
  needs a shared limiter. Model analysis stays sequential in this minimal change.

## Evidence before delivery

- Parser regression failed before the fix: an empty first Yandex item hid valid
  content in a later item. All nonempty items are now preserved and deduplicated;
  all-empty or broken content remains retryable rather than a negative verdict.
- Shared/client gates passed: 65 XMLRiver tests, 33 rules/LLM/clarification,
  52 pipeline/durable/billing/storage and 46 watchdog/readiness/timing checks;
  benchmark self-check and diff check passed.
- Initial batch server gate passed 119 tests. Independent review then reproduced
  two additional defects: one unexpected task cancelled paid siblings; throttle
  state did not cover later runs. Both are fixed in `b7b4c8d`; final full server
  gate passed 124 tests, including independent capture saves, failure drain,
  cooldown across runs and Google behind 21 blocked Yandex runs.
- Server retries use six attempts; the legacy agent keeps three. A typed
  HTTP 429/XML 115 throttle carries the documented 600-second delay and stays
  compatible with existing quota-error handlers.
- Production remains `09df3b7` until exact-source CI and normal image deployment
  pass. No migration or administrator SSH access is required for this change.
- New batch tests use fake providers and disposable SQLite. They do not prove
  PostgreSQL concurrency, model latency or live provider throughput.
- Cooldown lives in the single worker and resets on process restart. Account
  capacity is read once at startup; failure safely falls back to one per engine.
  A cooldown queue is read in keyset pages of 20; its scan time still grows with
  the number of queued projects. Saved answers drain before any fresh collection.
- A bounded live SDK follow-up on the two reported Yandex queries returned
  valid absence of an AI block in 3.781s (one attempt), while the other exhausted
  all six attempts with `XMLRiverResponseError` after 230.609s. This proves
  retries execute but does not prove upstream errors disappear. Safe metadata
  is outside Git in `~/.codex/tmp/xmlriver-release-20261009/speed-fixed-provider.json`;
  successful capture is DPAPI-encrypted. No text/model/billing scan was run.
