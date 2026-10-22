# Provider failure diagnostics

Base: production `d711aead8d1759309e660e09987bc039f5649e2c` (2026-10-22).

## Scope

Persist safe XMLRiver collection failure categories in the existing bounded provider
task history: timeout, transport, HTTP, API, malformed/incomplete response and
cancellation. Keep provider admission, retry timing, saved answers, ownership and
wallet settlement unchanged. Do not send additional live provider requests.

## Acceptance

- Distinguish failure stages and safe status/error codes without storing credentials,
  request URLs, prompt text, response bodies or arbitrary exception text.
- Retain the failed attempt's diagnostic across normal re-admission, bounded to the
  existing history limit; stale attempts cannot overwrite the current attempt.
- Cancellation remains cancellation; existing provider recovery and money gates pass.
- Release through a PR into production, exact-SHA CI, verified backup/isolated restore
  and live readiness. Observe a subsequent ordinary attempt without accelerating it.

## Evidence

Implementation: [PR #85](https://github.com/egotrippingh/aiparser/pull/85), merged as
`c21633d347f922f4da4ded5e0d23764b8589636d`. Shared XMLRiver/legacy checks: 71 passed; after the
ASCII-code normalization fix, the final XMLRiver text suite passed 34 tests.
Independent correctness and focused risk reviews found no blocking issues; an
independent narrow run passed 13 tests. Final additions cover stale/completed task
history and native cancellation. [PR CI](https://github.com/egotrippingh/aiparser/actions/runs/39820684000)
passed 423 server tests with PostgreSQL, 95 shared detection/XMLRiver tests, 137
frontend tests, lint/build, image smoke and delivery checks. A redundant local
Windows full-server run was stopped after the PostgreSQL CI passed; it had no
reported failures but was incomplete.

[Production delivery](https://github.com/egotrippingh/aiparser/actions/runs/39821835936)
passed for `c21633d347f922f4da4ded5e0d23764b8589636d`. The backup restored into an
isolated database; public readiness matched that exact SHA. A read-only in-container
smoke confirmed the installed diagnostic classifier and redaction. No live provider
request was sent for verification. Read-only verification at 2026-10-22 21:35 MSK
confirmed persisted diagnostics for three ordinary failed cycles: cycle14 at
20:42:53 and cycle15 at21:01:55 recorded XML API code500 (not HTTP status500);
cycle16 at21:21:10 recorded incomplete/missing_content (AI element present without
nonempty item content). Each diagnostic reports six HTTP attempts in its cycle.
The observed run remained69/70; the next submission was eligible from21:36:10 MSK.
These records identify the last failure in each cycle, not every HTTP response.
Previous attempt causes cannot be reconstructed retroactively.

Local test logs: `C:/codex-tmp/provider-failure-diagnostics-20261022/`.

The persisted diagnostic records category, fixed reason/provider numeric code,
optional HTTP status, stage, timestamp, durable cycle and HTTP-attempt count. It
shares the existing last-32-entry history; older transition entries remain readable.
No diagnostic field is exposed through a new public API or written to the Git tree.

## Explicitly authorized one-request investigation

On2026-10-22 the user authorized an additional paid-endpoint diagnostic request.
At21:43:31–21:44:03 MSK one GET with the frozen run/query/geography and `ai=1`
returned HTTP200,8418 bytes. The AI element contained one item with type/position
metadata and an empty content element, without alternative answer/text nodes.
Thirteen ordinary search-result documents were present outside the AI element.
The installed parser rejected this response as incomplete/missing_content;
no alternate AI answer was discarded in this observed response.

The bounded probe used no adapter retries, changed no project/result/billing rows,
and retained only sanitized tag paths, lengths/counts, safe error metadata and
timestamps. Raw XML, attribute values, prompts and response text were not saved.
Its structure/redaction self-check passed. Re-running the same probe reads its
saved outcome instead of sending another paid request.

Local safe structure: `C:/codex-tmp/provider-failure-diagnostics-20261022/xml-structure-one-paid-response.json`.
Remote safe structure: `/tmp/airate-xml-structure-20261022-one-paid-request.json`
inside the web container. Provider billing for the single diagnostic call was not
independently reconciled. No automatic monitor or further paid request was added.

The user then explicitly authorized a second single request and full untruncated
XML retention. At21:48:16–21:48:58 MSK it returned HTTP200 and a complete269-byte
XML API500 error, stating that no search-engine response was received. No adapter
retry was used. The full response was streamed without a size cutoff, transferred
as binary, checked against the server SHA-256 and kept outside Git:
`C:/codex-tmp/provider-failure-diagnostics-20261022/xmlriver-yandex-full-response-20261022.xml`.
The byte-preservation self-check passed. The response contained no configured API
key. The ordinary task/result/billing rows were not modified by either probe.
