# Brand detection quality — proposed experiment and implementation

Base: production `58f0271958352e1ec05aa2e4bb4c7b4737e089b7` (2026-10-17).
Branch: `codex/brand-detection-quality`. No publication. Initially the user authorized
only synthetic OpenRouter inputs; on 2026-10-17 expanded this to 300–500 admin-owned
server answers under the same shared USD 5 cap. Other users and credit purchases
remain excluded.

## Outcome and scope

- Goal: at least 90% precision and recall on separately labelled, held-out answers;
  report accuracy, coverage, uncertainty, per-provider slices, latency and API cost.
  Synthetic regression cases establish behavior, not production accuracy.
- Confirmed baseline failures: Альтодент/Альтодентал, Neighbors/Neighborbrite,
  Apple/fruit are accepted by rules and bypass semantic analysis/arbiter.
- Keep owner scope, captures, bounded attempts, caching, settlement, original history,
  current pricing and old protocol compatibility. No migrations or automatic recompute.

## Rules and routing

- A negative recommendation still mentions a brand. A question-only occurrence,
  another company, common noun or generic business role is not brand evidence.
- Own-domain sources keep the fast path unless identity clarification requires checking.
- Name/card/fuzzy/third-party URL matches are candidates, requiring identity checking
  by primary in smart mode. This costs additional calls and must be measured.
- Confident semantic negatives can reject lexical candidates. Explicitly low-confidence
  negatives and other unresolved cases reach a neutral arbiter, using original evidence.
  Missing optional confidence in legacy JSON is not an explicit uncertainty score.
- Never mode retains rules-only behavior. Existing clarification forcing is retained.
- Transport/schema/truncated-output failures must not silently become not_found or
  confirmed rule hits; preserve the existing capture/recovery and charging contracts.
- Use one strict verdict parser. Optional fields may be absent; supplied wrong types,
  nonfinite/out-of-range confidence and unsupported mention kinds are invalid.

## Work packets

1. Detector/server implementation and deterministic regressions: shared parser, rules,
   merge, cloud/legacy callers, neutral prompts, server-owned reasoning configuration.
2. Offline evaluation: synthetic cases and a scorer for saved independent predictions;
   reject duplicates/unknown IDs and count missing/error predictions in coverage.
3. Research Gemini, DeepSeek, Qwen and GLM prices/settings; compare them on the same
   24 synthetic cases. Record exact model/provider/reasoning and all attempted costs.
   Standalone classification screens candidates; it does not measure production routing.
4. Independent correctness and billing/recovery review; fix verified defects, run
   affected tests and full server gates. Prepare a PR into production.

## Evaluation contract

- Split by brand/project and near-duplicate answer before tuning; holdout labels are
  human-reviewed, with ambiguous identity cases adjudicated separately.
- Cases cover text, aliases/translit, domain, dealer URL, cards, indirect evidence,
  same-name companies, common words, query-only mentions, injection and capture failure.
- Never use model confidence or an LLM judge as the ground-truth label. Keep held-out
  examples out of project feedback/few-shot prompts used in the same evaluation.
- Report confusion counts and precision/recall with sample counts and confidence
  intervals. Undefined metrics remain undefined; errors are not silently excluded.
- Preserve current production defaults while preparing reasoning controls. Model
  choice and expanded-route cost/latency remain unverified until the live experiment.

## Checks and open decisions

- Baseline: 35 existing detection/parser/clarification/AI tests passed; three synthetic
  false-positive probes reproduced. Independent planning/refutation completed.
- Remaining decisions: labelled real corpus,
  latency/cost acceptance and whether a third-party URL alone establishes visibility.
- Actual historical statuses, prices and production model settings remain unchanged.

## Offline scorer (prepared)

`python scripts/evaluate_brand_detection.py --cases tests/fixtures/brand_detection_cases.jsonl --predictions path/to/candidate.jsonl --output path/to/report.json`

Each prediction has a matching `id`, boolean `found` for a decision, or `found:null`
with a nonempty `error`. Optional `cost_usd` and `latency_s` cover the whole attempted
pipeline, including retries and arbiter. One file per candidate; multiple files may
be passed to `--predictions`. No API call, key lookup or production database access.

Missing/error decisions lower end-to-end accuracy and coverage; positive errors also
lower recall. Precision uses actual positive decisions. Unknown/duplicate IDs and
invalid types are rejected. Unknown cost stays unknown, not zero. Wilson 95% intervals
and per-brand/category/provider slices accompany scores. Numerical target checks are
not a certification of representative, independent human labels.

The 24 initial cases are synthetic development fixtures, not a holdout. Gold-label
echoes in the scorer's CLI test verify arithmetic only. Scorer checks: 16 passed.

## Price assessment requested

Evaluate retail 1.50 RUB per query/service without changing the current price. Include
actual collector/actor pricing, nonbilled-result costs, retry amplification, primary
and arbiter token usage, credit/FX/payment fees, hosting/storage and tax assumptions.
Distinguish contribution margin from net profit; show FX and heavy-answer sensitivity.
Actual token distributions, arbitration share, private discounts and FX purchase rate
remain unknown until a scoped experiment/accounting input is available.

## Prepared result

An authorized 168-request synthetic run and 24-case cheaper-model control completed.
[Results and model choice](../brand-model-comparison.md),
[economics](../brand-detection-economics.md), [review PR #74](https://github.com/egotrippingh/aiparser/pull/74).
Known usage $0.057090601164; conservative total reservation $3.2131664388 under $5.
No representative human accuracy claim or publication. Default models and current price unchanged.
Deterministic checks: 68 detection/evaluation/workflow, 22 planner, 6 AI adapter,
6 cache/budget and 2 cloud-card cases passed. Independent correctness/risk reviews
found no remaining blocker; latest full CI evidence belongs in the PR.

## Expanded server-answer audit (authorized 2026-10-17)

User requested 300–500 server answers and confirmed there is no human gold labelling.
This is a blind agreement/error audit, never accuracy/precision/recall measurement.
Production data is read-only; no statuses, feedback, billing or runtime models change.

- Only the admin account's five managed providers: 2487 completed captures with frozen
  run identity/query. Other users and legacy Alice are excluded. Exclude seven feedback
  results and same-query variants (93 captures); no feedback examples enter the prompt.
- Frozen stratified selection: 300 answers, 60 per provider, three brands; historical
  statuses 117 found / 183 not_found are sampling metadata, never gold or model inputs.
  Text/cards/sources only; source-card title/text is folded into separate card evidence.
  Screenshots and fetched source pages are outside this audit.
- Two independent calls per answer: Qwen3.8 Flash (reasoning budget 512) and Pro-0813
  (effort=none), max output 1024, alternating paired order, four workers, no retries.
  Provider hard caps: Qwen $0.15/$0.47 and Pro $0.66/$1.98 per million tokens.
- Shared original $5 cap: prior cost upper bound rounded up to $0.294; all 600 new
  request ceilings total $4.503357972. Entire $4.797357972 is reserved before any POST.
  Incomplete runs retain the full reservation; never rerun with the old bound alone.
- Inputs, original IDs, quotes and individual decisions stay in ignored local private
  files. Publish aggregate coverage, disagreement, cost and latency only. Review samples
  remain AI-assisted qualitative analysis, not human gold. No auto-correction of reports.

Audit script/cost/coverage safeguards passed 12 deterministic tests and independent
correctness/risk rechecks before paid dispatch. The 600-call run completed: Qwen 294/300
valid, Pro 288/300; 283 complete pairs, 282 agreements and one disagreement. These
are coverage/agreement, not accuracy. [Aggregate evidence](../brand-model-audit.md).
New known cost USD 0.262573952328; full unknown-request ceilings USD 0.167426622.
Shared prior-plus-new upper bound USD 0.724000574328 remains under USD 5.
Source CI on 4da1a05 passed: https://github.com/egotrippingh/aiparser/actions/runs/39029556855.
Blinded private web review is ready; user will label later and explicitly requested a
pause after the run. Phone review cancelled, no human label received. Await human
JSONL before quality metrics, further paid tests, model activation or publication.
