"""Explicitly opt-in, price-capped OpenRouter probe of synthetic brand fixtures."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_brand_detection import load_rows, score  # noqa: E402
from server.ai import PRIMARY_SYSTEM  # noqa: E402
from shared.detection import _build_prompt, parse_verdict  # noqa: E402

# Provider prices are hard filters in USD/million tokens, not assumed actual costs.
CANDIDATES = {
    "lite": ("google/gemini-3.1-flash-lite", {"effort": "minimal"}, "0.5", "3"),
    "flash": ("google/gemini-3.8-flash", {"effort": "low"}, "1.65", "8.25"),
    "deepseek-pro": ("deepseek/deepseek-v4-pro-0813", {"effort": "low"}, "1.32", "3.96"),
    "deepseek-pro-none": ("deepseek/deepseek-v4-pro-0813", {"effort": "none"}, "1.32", "3.96"),
    "deepseek-flash": ("deepseek/deepseek-v4.1-flash-1017", {"effort": "low"}, "0.3", "1.2"),
    "qwen": ("qwen/qwen3.8-flash", {"max_tokens": 512}, "0.3", "0.94"),
    "glm": ("z-ai/glm-5.3-flash", {"effort": "low"}, "0.3", "1"),
}


class Budget:
    def __init__(self, maximum: Decimal):
        if not maximum.is_finite() or not Decimal("0") < maximum <= Decimal("5"):
            raise ValueError("Maximum spend must be greater than 0 and at most USD 5")
        self.maximum = maximum
        self.reserved = Decimal("0")

    def admit(self, ceiling: Decimal) -> bool:
        if not ceiling.is_finite() or ceiling <= 0:
            raise ValueError("Invalid request ceiling")
        if self.reserved + ceiling > self.maximum:
            return False
        self.reserved += ceiling
        return True


def payload_for(case: dict, candidate: tuple, max_tokens: int, metadata: dict) -> dict:
    model, reasoning, input_cap, output_cap = candidate
    prompt = _build_prompt(case["brand_name"], case.get("aliases", []), case["answer_text"],
        case.get("sources", []), case.get("query"), case.get("brand_clarification", ""),
        case.get("domains", []), text_only=True, cards_text=case.get("cards_text", ""))
    payload = {"model": model, "messages": [{"role": "system", "content": PRIMARY_SYSTEM},
                                             {"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "response_format": {"type": "json_object"},
               "reasoning": {**reasoning, "exclude": True}, "usage": {"include": True},
               "provider": {"max_price": {"prompt": float(input_cap), "completion": float(output_cap), "request": 0},
                            "require_parameters": True}}
    if "temperature" in metadata.get("supported_parameters", []):
        payload["temperature"] = 0
    return payload


def request_ceiling(payload: dict) -> Decimal:
    # Byte count bounds text tokens conservatively; reserve framing and output slack.
    input_tokens = len(json.dumps(payload["messages"], ensure_ascii=False).encode("utf-8")) + 1024
    limits = payload["provider"]["max_price"]
    raw = (Decimal(input_tokens) * Decimal(str(limits["prompt"])) +
           Decimal(payload["max_tokens"] + 256) * Decimal(str(limits["completion"]))) / Decimal(1_000_000)
    return raw * Decimal("1.08")


def call(client: httpx.Client, case_id: str, payload: dict) -> dict:
    start = time.monotonic()
    record = {"id": case_id, "found": None, "model": payload["model"], "cost_usd": None,
              "budget_ceiling_usd": float(request_ceiling(payload))}
    try:
        response = client.post("https://openrouter.ai/api/v1/chat/completions", json=payload)
        if response.status_code != 200:
            record["error"] = f"http_{response.status_code}"
            return record
        data = response.json()
        usage = data.get("usage") or {}
        if isinstance(usage, dict):
            cost = usage.get("cost")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
                record["cost_usd"] = cost
            for name in ("prompt_tokens", "completion_tokens"):
                record[name] = usage.get(name)
            details = usage.get("completion_tokens_details") or {}
            record["reasoning_tokens"] = details.get("reasoning_tokens") if isinstance(details, dict) else None
        choice = data["choices"][0]
        record["provider"] = data.get("provider")
        record["returned_model"] = data.get("model")
        record["finish_reason"] = choice.get("finish_reason")
        if record["finish_reason"] == "length":
            record["error"] = "truncated"
        else:
            verdict = parse_verdict(choice["message"].get("content"), payload["model"])
            if verdict is None:
                record["error"] = "invalid_verdict"
            else:
                record.update(found=verdict.found, confidence=verdict.confidence,
                              quote=verdict.quote[:1000], reasoning=verdict.reasoning[:1000])
    except httpx.HTTPError as exc:
        record["error"] = type(exc).__name__
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        record["error"] = "invalid_response"
    finally:
        record["latency_s"] = time.monotonic() - start
    return record


def run(cases: dict[str, dict], names: list[str], client: httpx.Client, metadata: dict,
        budget: Budget, output: Path, *, max_tokens: int = 4096, workers: int = 3) -> dict:
    if not 1 <= len(cases) <= 24 or any(row.get("label_source") != "synthetic" or row.get("split") != "dev" for row in cases.values()):
        raise ValueError("This probe is limited to at most 24 synthetic development cases")
    if not 128 <= max_tokens <= 4096 or not 1 <= workers <= 4:
        raise ValueError("Probe output limit is 128..4096 tokens; workers 1..4")
    if not names or len(names) != len(set(names)) or any(name not in CANDIDATES for name in names):
        raise ValueError("Choose distinct known candidate names")
    # Verify the gold schema locally; no expected labels are included in API messages.
    score(cases, {})
    for name in names:
        model, reasoning, *_ = CANDIDATES[name]
        if model not in metadata or "response_format" not in metadata[model].get("supported_parameters", []):
            raise ValueError(f"JSON-capable model unavailable: {model}")
        efforts = (metadata[model].get("reasoning") or {}).get("supported_efforts")
        if efforts and reasoning.get("effort") not in efforts:
            raise ValueError(f"Unsupported reasoning setting: {name}")
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for name in names:
        predictions = {}
        with (output / f"{name}.jsonl").open("x", encoding="utf-8") as stream, ThreadPoolExecutor(max_workers=workers) as pool:
            for offset in range(0, len(cases), workers):
                jobs = []
                for case in list(cases.values())[offset:offset + workers]:
                    payload = payload_for(case, CANDIDATES[name], max_tokens, metadata[CANDIDATES[name][0]])
                    if budget.admit(request_ceiling(payload)):
                        jobs.append((case["id"], pool.submit(call, client, case["id"], payload)))
                    else:
                        jobs.append((case["id"], None))
                for case_id, job in jobs:
                    record = job.result() if job else {"id": case_id, "found": None, "error": "budget_not_admitted"}
                    predictions[case_id] = record
                    stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
                    stream.flush()
        reports.append({"candidate": name, "model": CANDIDATES[name][0],
                        "reasoning_setting": CANDIDATES[name][1], **score(cases, predictions)})
        print(json.dumps({"candidate": name, "overall": reports[-1]["overall"],
                          "known_cost_usd": reports[-1]["known_cost_usd"],
                          "reserved_ceiling_usd": str(budget.reserved)}), flush=True)
    result = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "standalone classification of synthetic dev cases, not end-to-end production accuracy",
              "primary_prompt_sha256": hashlib.sha256(PRIMARY_SYSTEM.encode()).hexdigest(),
              "max_output_tokens": max_tokens, "workers": workers,
              "budget_usd": str(budget.maximum), "reserved_ceiling_usd": str(budget.reserved),
              "models": {model: metadata[model] for model in {CANDIDATES[name][0] for name in names}},
              "reports": reports}
    (output / "report.json").write_text(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly permit paid API calls")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="Must not already exist")
    parser.add_argument("--models", nargs="+", choices=CANDIDATES, default=list(CANDIDATES))
    parser.add_argument("--max-cost-usd", type=Decimal, required=True)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not args.run or not key:
        parser.error("--run and an existing OPENROUTER_API_KEY are required; this script never buys credits")
    try:
        cases, budget = load_rows(args.cases), Budget(args.max_cost_usd)
        with httpx.Client(timeout=90, headers={"Authorization": "Bearer " + key, "X-Title": "AIRate synthetic model comparison"}) as client:
            response = client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            metadata = {row["id"]: row for row in response.json()["data"]}
            run(cases, args.models, client, metadata, budget, args.output_dir,
                max_tokens=args.max_tokens, workers=args.workers)
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.error(type(exc).__name__ + ": probe could not complete; existing results are preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
