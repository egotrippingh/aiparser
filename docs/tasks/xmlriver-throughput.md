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
