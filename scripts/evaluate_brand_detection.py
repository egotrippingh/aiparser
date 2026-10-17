"""Score saved brand-detector predictions offline, without credentials or API calls."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def load_rows(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path.name}:{number}: invalid JSON") from exc
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
                raise ValueError(f"{path.name}:{number}: a nonempty string id is required")
            if row["id"] in rows:
                raise ValueError(f"{path.name}:{number}: duplicate id {row['id']}")
            rows[row["id"]] = row
    return rows


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def wilson(successes: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = 1.959963984540054
    rate = successes / count
    scale = 1 + z * z / count
    center = (rate + z * z / (2 * count)) / scale
    radius = z * math.sqrt(rate * (1 - rate) / count + z * z / (4 * count * count)) / scale
    return [max(0.0, center - radius), min(1.0, center + radius)]


def metrics(cases: list[dict], predictions: dict[str, dict]) -> dict:
    tp = fp = tn = fn = positive_errors = negative_errors = 0
    for case in cases:
        prediction = predictions.get(case["id"], {})
        found = prediction.get("found")
        if found is None or prediction.get("error"):
            if case["expected"]:
                positive_errors += 1
            else:
                negative_errors += 1
        elif case["expected"]:
            if found:
                tp += 1
            else:
                fn += 1
        elif found:
            fp += 1
        else:
            tn += 1
    total = len(cases)
    decided = tp + fp + tn + fn
    return {
        "total": total, "decided": decided, "errors_or_missing": total - decided,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "positive_errors": positive_errors, "negative_errors": negative_errors,
        "coverage": ratio(decided, total),
        "accuracy": ratio(tp + tn, total),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn + positive_errors),
        "conditional_accuracy": ratio(tp + tn, decided),
        "accuracy_ci95": wilson(tp + tn, total),
        "precision_ci95": wilson(tp, tp + fp),
        "recall_ci95": wilson(tp, tp + fn + positive_errors),
    }


def score(cases: dict[str, dict], predictions: dict[str, dict], *, target: float = 0.9) -> dict:
    if not cases:
        raise ValueError("No labelled cases")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or not 0 < target <= 1:
        raise ValueError("Target must be a finite number in (0, 1]")
    for case in cases.values():
        if not isinstance(case.get("expected"), bool):
            raise ValueError(f"Case {case['id']}: expected must be boolean")
        for field in ("brand_name", "category", "provider", "split", "label_source"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f"Case {case['id']}: {field} must be a nonempty string")
        if case["label_source"] not in {"synthetic", "human"} or case["split"] not in {"dev", "holdout"}:
            raise ValueError(f"Case {case['id']}: unknown label_source or split")
    unknown = predictions.keys() - cases.keys()
    if unknown:
        raise ValueError(f"Predictions contain unknown case ids: {', '.join(sorted(unknown))}")
    for case_id, prediction in predictions.items():
        found, error = prediction.get("found"), prediction.get("error")
        if found is not None and not isinstance(found, bool):
            raise ValueError(f"Prediction {case_id}: found must be boolean or null")
        if error is not None and (not isinstance(error, str) or not error.strip()):
            raise ValueError(f"Prediction {case_id}: error must be a nonempty string")
        if error and found is not None:
            raise ValueError(f"Prediction {case_id}: an error cannot also be a decision")
        for field in ("cost_usd", "latency_s"):
            value = prediction.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                raise ValueError(f"Prediction {case_id}: invalid {field}")
    overall = metrics(list(cases.values()), predictions)
    holdout_cases = [row for row in cases.values() if row["label_source"] == "human" and row["split"] == "holdout"]
    holdout = metrics(holdout_cases, predictions) if holdout_cases else None
    costs = [row["cost_usd"] for row in predictions.values() if row.get("cost_usd") is not None]
    latencies = sorted(row["latency_s"] for row in predictions.values() if row.get("latency_s") is not None)
    slices = {}
    for field in ("category", "provider", "brand_name", "label_source", "split"):
        slices[field] = {value: metrics([row for row in cases.values() if row[field] == value], predictions)
                         for value in sorted({row[field] for row in cases.values()})}
    return {
        "scope": "Saved predictions only; representativeness and label independence require human review.",
        "human_holdout_only": all(row["label_source"] == "human" and row["split"] == "holdout" for row in cases.values()),
        "target": target,
        "all_cases_meet_numeric_target": all(overall[key] is not None and overall[key] >= target for key in ("accuracy", "precision", "recall")),
        "human_holdout_meets_target": all(holdout[key] is not None and holdout[key] >= target for key in ("accuracy", "precision", "recall")) if holdout else None,
        "human_holdout_lower_bounds_meet_target": all(holdout[key] is not None and holdout[key][0] >= target for key in ("accuracy_ci95", "precision_ci95", "recall_ci95")) if holdout else None,
        "overall": overall, "human_holdout": holdout, "slices": slices,
        "known_cost_usd": sum(costs) if costs else None,
        "cost_records": len(costs), "cost_coverage": ratio(len(costs), len(cases)),
        "latency_records": len(latencies),
        "latency_p50_s": statistics.median(latencies) if latencies else None,
        "latency_p95_s": latencies[math.ceil(len(latencies) * 0.95) - 1] if latencies else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="Labelled JSONL cases")
    parser.add_argument("--predictions", type=Path, nargs="+", required=True, help="One saved JSONL file per candidate")
    parser.add_argument("--target", type=float, default=0.9)
    parser.add_argument("--output", type=Path, help="Save aggregate JSON; raw answers are never printed")
    args = parser.parse_args()
    try:
        if args.output and any(args.output.resolve() == path.resolve() or
                               (args.output.exists() and args.output.samefile(path))
                               for path in [args.cases, *args.predictions]):
            parser.error("Output must not replace cases or predictions")
        cases = load_rows(args.cases)
        reports = [{"predictions_file": str(path), **score(cases, load_rows(path), target=args.target)}
                   for path in args.predictions]
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(reports, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    try:
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
    except OSError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
