"""Private, capped blind-agreement audit of unlabelled captured answers."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
import statistics
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_brand_models import Budget, call, payload_for, request_ceiling
from server.ai import PRIMARY_SYSTEM

# Rounded up: known usage + full unknown-response ceilings from the 192-case experiment.
# See docs/evidence/brand-model-comparison-2026-10-17.json. A rerun needs its new bound too.
MINIMUM_PREVIOUS = Decimal('0.294')

CANDIDATES = {
    "qwen3.8-flash": ("qwen/qwen3.8-flash", {"max_tokens": 512}, "0.15", "0.47"),
    "deepseek-pro-0813": ("deepseek/deepseek-v4-pro-0813", {"effort": "none"}, "0.66", "1.98"),
}
REQUIRED = {"id", "brand_name", "answer_text"}
OPTIONAL_STR = {"cards_text", "query", "brand_clarification", "provider", "project"}
OPTIONAL_LIST = {"aliases", "domains", "sources"}


def load_cases(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    validate_cases(rows)
    return rows


def validate_cases(rows: list[dict]) -> None:
    if not 300 <= len(rows) <= 500:
        raise ValueError("Audit requires 300..500 unlabelled cases")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not REQUIRED <= row.keys() or set(row) - (REQUIRED | OPTIONAL_STR | OPTIONAL_LIST):
            raise ValueError("Invalid or non-whitelisted case field")
        if any(not isinstance(row[key], str) or not row[key].strip() for key in REQUIRED) or row["id"] in seen:
            raise ValueError("Case IDs and required fields must be nonempty strings")
        if any(key in row and not isinstance(row[key], str) for key in OPTIONAL_STR):
            raise ValueError("Optional text fields must be strings")
        if any(key in row and (not isinstance(row[key], list) or any(not isinstance(v, str) for v in row[key])) for key in OPTIONAL_LIST):
            raise ValueError("Optional list fields must contain strings")
        if (len(row['id']) > 100 or len(row['brand_name']) > 120 or len(row['answer_text']) > 60000
                or len(row.get('cards_text', '')) > 60000 or len(row.get('query', '')) > 4000
                or len(row.get('brand_clarification', '')) > 2000):
            raise ValueError('Oversized input')
        for key in OPTIONAL_LIST:
            if len(row.get(key, [])) > (50 if key == 'sources' else 100) or any(len(v) > 4000 for v in row.get(key, [])):
                raise ValueError('Oversized evidence list')
        seen.add(row["id"])


def audit_payload(case: dict, candidate: tuple, metadata: dict) -> dict:
    evidence = {key: value for key, value in case.items() if key not in {'id', 'provider', 'project'}}
    return payload_for(evidence, candidate, 1024, metadata)


def usage_summary(records: list[dict], expected: int) -> dict:
    decided = sum(isinstance(row.get('found'), bool) and not row.get('error') for row in records)
    costs = [row['cost_usd'] for row in records if row.get('cost_usd') is not None]
    unknown = sum(row['budget_ceiling_usd'] for row in records if row.get('cost_usd') is None)
    latencies = sorted(row['latency_s'] for row in records if row.get('latency_s') is not None)
    return {'expected': expected, 'attempted': len(records), 'decided': decided,
        'errors': len(records) - decided, 'missing': expected - len(records),
        'decision_coverage': decided / expected if expected else None,
        'known_cost_usd': sum(costs) if costs else None, 'cost_records': len(costs),
        'unknown_cost_request_ceiling_usd': unknown,
        'known_plus_unknown_ceiling_usd': sum(costs) + unknown,
        'latency_p50_s': statistics.median(latencies) if latencies else None,
        'latency_p95_s': latencies[math.ceil(len(latencies) * .95) - 1] if latencies else None,
        'prompt_tokens_reported': sum(row.get('prompt_tokens') or 0 for row in records),
        'completion_tokens_reported': sum(row.get('completion_tokens') or 0 for row in records),
        'reasoning_tokens_reported': sum(row.get('reasoning_tokens') or 0 for row in records)}


def report(cases: list[dict], records: list[dict]) -> dict:
    pairs = {case['id']: {} for case in cases}
    for record in records:
        if record.get('id') not in pairs or record.get('candidate') not in CANDIDATES:
            raise ValueError('Unknown prediction ID or candidate')
        if record['candidate'] in pairs[record['id']]:
            raise ValueError('Duplicate prediction')
        if record.get('found') is not None and not isinstance(record['found'], bool):
            raise ValueError('Invalid decision')
        if record.get('error') and record.get('found') is not None:
            raise ValueError('Failed prediction cannot also be a decision')
        pairs[record['id']][record['candidate']] = record
    table = {key: 0 for key in ("q+_p+", "q+_p-", "q-_p+", "q-_p-")}
    both = 0
    for pair in pairs.values():
        q, p = pair.get("qwen3.8-flash"), pair.get("deepseek-pro-0813")
        if q and p and all(isinstance(row.get('found'), bool) and not row.get('error') for row in (q, p)):
            both += 1
            table[f"q{'+' if q['found'] else '-'}_p{'+' if p['found'] else '-'}"] += 1
    return {'total_cases': len(cases), 'both_decided': both,
        'both_decision_coverage': both / len(cases) if cases else None,
        'agreement_among_both_decided': None if not both else (table['q+_p+'] + table['q-_p-']) / both,
        'table': table,
        'per_candidate': {name: usage_summary([r for r in records if r['candidate'] == name], len(cases)) for name in CANDIDATES},
        'all_attempts': usage_summary(records, len(cases) * len(CANDIDATES))}


def run(cases: list[dict], client: httpx.Client, metadata: dict, budget: Budget, previous: Decimal, output: Path, workers=4):
    validate_cases(cases)
    if not previous.is_finite() or not MINIMUM_PREVIOUS <= previous <= budget.maximum:
        raise ValueError('Previous bound must include the prior experiment (at least USD 0.294)')
    if budget.reserved != 0 or not 1 <= workers <= 4:
        raise ValueError('Use a fresh budget and 1..4 workers')
    if output.exists():
        raise FileExistsError(output)
    for model, reasoning, *_ in CANDIDATES.values():
        info = metadata.get(model, {})
        if not {'response_format', 'reasoning'} <= set(info.get('supported_parameters', [])):
            raise ValueError('JSON/reasoning-capable candidate metadata unavailable')
        efforts = (info.get('reasoning') or {}).get('supported_efforts')
        if efforts and reasoning.get('effort') not in efforts:
            raise ValueError('Unsupported reasoning setting')
    payloads = []
    for index, case in enumerate(cases):
        # Alternate order across pairs, but keep both calls on identical original evidence.
        names = list(CANDIDATES)
        if index % 2:
            names.reverse()
        for name in names:
            model = CANDIDATES[name][0]
            if model not in metadata:
                raise ValueError("Candidate metadata unavailable")
            payload = audit_payload(case, CANDIDATES[name], metadata[model])
            ceiling = request_ceiling(payload)
            payloads.append((case, name, payload, ceiling))
    if not budget.admit(previous):
        raise ValueError('Prior spend exceeds budget')
    for _, _, _, ceiling in payloads:
        if not budget.admit(ceiling):
            raise ValueError('Whole audit ceiling exceeds maximum; no model calls made')
    output.mkdir(parents=True, exist_ok=False)
    result = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'blind agreement audit; no labels or accuracy estimate',
        'previous_cost_bound_usd': str(previous), 'maximum_shared_usd': str(budget.maximum),
        'reserved_new_ceiling_usd': str(budget.reserved - previous),
        'reserved_shared_ceiling_usd': str(budget.reserved), 'expected_requests': len(payloads),
        'max_output_tokens': 1024, 'workers': workers, 'automatic_retries': 0,
        'input_sha256': hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        'primary_prompt_sha256': hashlib.sha256(PRIMARY_SYSTEM.encode()).hexdigest(),
        'models': CANDIDATES, 'metadata': metadata, 'completed': False}
    manifest = output / 'manifest.json'
    manifest.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    records = []
    with (output / "predictions-private.jsonl").open("x", encoding="utf-8") as stream, ThreadPoolExecutor(max_workers=workers) as pool:
        for offset in range(0, len(payloads), workers):
            batch = payloads[offset:offset + workers]
            jobs = []
            for case, name, payload, _ in batch:
                jobs.append((case["id"], name, pool.submit(call, client, case["id"], payload)))
            for case_id, name, job in jobs:
                record = job.result(); record["candidate"] = name
                records.append(record); stream.write(json.dumps(record, allow_nan=False) + "\n"); stream.flush()
            if len(records) % 20 == 0:
                print(json.dumps({'completed_requests': len(records), 'expected_requests': len(payloads)}), flush=True)
    summary = report(cases, records)
    summary['slices'] = {}
    for field in ('provider', 'project'):
        summary['slices'][field] = {}
        for value in sorted({case.get(field, 'unknown') for case in cases}):
            group = [case for case in cases if case.get(field, 'unknown') == value]
            ids = {case['id'] for case in group}
            summary['slices'][field][value] = report(group, [r for r in records if r['id'] in ids])
    result.update(completed=True, completed_at_utc=datetime.now(timezone.utc).isoformat(), report=summary)
    manifest.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'completed_requests': len(records), 'both_decided': summary['both_decided'],
                     'agreement_among_both_decided': summary['agreement_among_both_decided'],
                     'reserved_shared_ceiling_usd': str(budget.reserved)}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cases", "output_dir"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    parser.add_argument("--run", action="store_true"); parser.add_argument("--max-cost-usd", type=Decimal, required=True)
    parser.add_argument("--previous-cost-bound-usd", type=Decimal, required=True)
    args = parser.parse_args()
    if not args.run or not os.environ.get("OPENROUTER_API_KEY"):
        parser.error("--run and OPENROUTER_API_KEY are required")
    cases = load_cases(args.cases); budget = Budget(args.max_cost_usd)
    prior = args.previous_cost_bound_usd
    if not prior.is_finite() or not MINIMUM_PREVIOUS <= prior <= budget.maximum:
        parser.error('Invalid prior experiment bound')
    with httpx.Client(timeout=90, headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], 'X-Title': 'AIRate private blind audit'}) as client:
        response = client.get('https://openrouter.ai/api/v1/models')
        response.raise_for_status()
        ids = {candidate[0] for candidate in CANDIDATES.values()}
        run(cases, client, {row['id']: row for row in response.json()['data'] if row['id'] in ids}, budget, prior, args.output_dir)


if __name__ == "__main__": main()
