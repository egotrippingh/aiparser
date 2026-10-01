# Empirical scan timing, 1 October 2026

## Scope and acceptance

Tune the existing **fast** profile for ChatGPT, Alice and Google AI Overview
using disposable copies of saved browser profiles. Preserve exact query input,
complete answers, capture, CAPTCHA handling, billing and parallel execution.
Perplexity is excluded: no paid account is available. New scans automatically
use the measured fast timing; unfinished scans keep their recorded timing. Legacy
profiles remain in stored/API data for compatibility.

A candidate must submit the exact query and keep the captured raw answer and
extracted source list unchanged in a follow-up observation five seconds after
capture. Failures and unverified extraction cannot count as successful trials.
Record effective provider timing in the scan snapshot; continuation must reuse
the stored timing, including legacy snapshots.

## Selected settings

| Provider | Between queries | Speed multiplier |
| --- | --- | --- |
| ChatGPT | 10–15 s, existing adapter floor | 0.20 |
| Alice | 1–2 s | 0.20 |
| Google AI Overview | 1–2 s | 0.20 |
| Perplexity | Unchanged: fast 2–5 s | Unchanged: 0.40 |

Previously fast used 0.40 and 2–5 s, with the same ChatGPT floor. The multiplier
controls typing and the adapter's existing preparation/scroll pauses. Character
delay changes from 22–70 ms to 11–35 ms; punctuation, corrected typos and scroll
steps remain. This halves artificial input delays, not provider generation or
network time. New scans use these settings automatically; existing unfinished
scans retain their recorded settings.

## Evidence and limits

Private evidence is ignored under `build/qa/`; browser state and raw answers are
not committed. All runs used direct adapters, outside repository scan creation
and billing. Originals were never overwritten. ChatGPT needed a manual login
in its copied test profile; authenticated trials used that copy.

| Trial | Result |
| --- | --- |
| Alice baseline, 0.40, two short queries | Raw text stable; typing 3.687 / 7.109 s. Later sources were not measured in this early utility version. |
| Google baseline, 0.40, two short queries | Raw text and extracted source list stable; typing 2.594 / 6.656 s. |
| ChatGPT baseline after login, 0.40 | One stable answer; typing 1.812 s. Second query failed, so no reliable total-time comparison. |
| ChatGPT selected, 0.20, three queries | 3/3 raw/source comparisons stable, including long answer: 6094 raw characters, 12 extracted sources. Typing 1.297 / 1.984 / 8.110 s. |
| Alice selected after completion fix, three queries | 3/3 raw/source comparisons stable: 3143/3952/7208 raw characters, 15/17/40 sources. Typing 1.203 / 2.016 / 7.641 s. |
| Google selected, initial four short queries | 4/4 raw/source comparisons stable; typing 1.141 / 1.781 / 1.110 / 1.703 s. Extracted source lists were empty. |
| Google subsequent long query, old completion logic | Failed: 4159 raw characters became 4616 after capture. |
| Google final conservative settle, short and long queries | 2/2 raw/source comparisons stable: 1506/4272 raw characters; typing 1.094/6.953 s; ask + capture 20.125/24.234 s. Extracted source lists were empty. |
| Google final source e9ae7c2, long query | Stable 4281 raw characters; typing 7.031 s, ask + capture 25.265 s. Extracted source list remained empty. |

Relevant folders: `scan-baseline-20260930-alice-01`,
`scan-baseline-20260930-google_aio-01`, `scan-baseline-20260930-chatgpt-03`,
`scan-typing-20261001-chatgpt-04`, `scan-fixed-20261001-alice-03`,
`scan-typing-20260930-google-02`, `scan-final-20261001-google-04`,
`scan-fixed-20261001-google-06`, `scan-fixed-20261001-google-07`.

Rejected experiments: multiplier 0.10 with 0.5–1 s pauses had incomplete/error
trials; replacing Google's networkidle wait also had failed trials. These do
not prove that the shorter delays caused the failures. Production networkidle
remains unchanged; the user's VPN makes its duration variable. Total elapsed
times also vary with generated answer length, so no universal percentage gain
or long-term rate-limit safety is established. These are the fastest tested
complete candidates in this small sample, not a global optimum. Empty Google
source lists do not prove preservation of nonempty lists.

## Completion repairs

Alice could stop changing for over six seconds while the visible “Алиса, стоп”
control was still active. It now waits for the observed generation marker to
disappear, compares complete text rather than length, and errors on timeout
instead of saving a partial answer. If the marker was never seen, the existing
quiet/source readiness fallback remains.

Google previously settled before expansion and could miss final paragraphs.
It now expands first, moves the pointer away, and requires five seconds of
unchanged full text. A candidate completed-disclaimer marker was rejected:
another observed DOM variant had no completion attributes anywhere, and two
queries timed out. No universal completion signal is established. The quiet
interval remains a heuristic; unusually long generation pauses can still fool
it. A 60 s settlement timeout raises an error; an overview that never appears
remains a valid absent result.
The expand control is checked again at settlement in case it arrived after the
initial heading; clicking it restarts text settling before capture.

## Reproduction

Run from the repository with its existing virtual environment. Output must be a
fresh folder outside the source profiles. Close the relevant profile first.

```powershell
.venv/Scripts/python.exe -X utf8 scripts/benchmark_scans.py --self-check
.venv/Scripts/python.exe -X utf8 scripts/benchmark_scans.py --output build/qa/my-fresh-trial --services alice google_aio --typing 0.2 --delay 1,2 --headless
```

For ChatGPT supply `--profiles` pointing to an authenticated copied profile.
Inter-query pauses still apply its 10–15 s adapter floor. The utility records
timings, counts and hashes; failed evidence stays local. Default services exclude
Perplexity. Deterministic checks cover timing routing, continuation, generation
pauses, equal-length text replacement, timeouts and benchmark input/outcomes.
