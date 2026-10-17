import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.evaluate_brand_detection import load_rows, score


def cases():
    return {name: {"id": name, "expected": expected, "brand_name": "SyntheticBrand",
                   "category": "text", "provider": "synthetic", "split": "dev", "label_source": "synthetic"}
            for name, expected in [("tp", True), ("fn", True), ("fp", False), ("tn", False), ("error", True)]}


def test_errors_and_missing_predictions_reduce_end_to_end_score():
    predictions = {name: {"found": found, "latency_s": 1, "cost_usd": 0.01}
                   for name, found in [("tp", True), ("fn", False), ("fp", True), ("tn", False)]}
    report = score(cases(), predictions)
    result = report["overall"]
    assert result["accuracy"] == 2 / 5
    assert result["coverage"] == 4 / 5
    assert result["precision"] == 1 / 2
    assert result["recall"] == 1 / 3
    assert result["positive_errors"] == 1
    assert result["conditional_accuracy"] == 1 / 2
    assert not report["human_holdout_only"] and not report["all_cases_meet_numeric_target"]
    assert report["human_holdout_meets_target"] is None
    assert report["known_cost_usd"] == 0.04 and report["cost_coverage"] == 4 / 5
    assert report["slices"]["provider"]["synthetic"] == result


def test_undefined_metrics_and_unknown_cost_are_not_zero_or_perfect():
    rows = cases()
    report = score(rows, {"error": {"error": "timeout", "cost_usd": 0.02}})
    assert report["overall"]["precision"] is None
    assert report["overall"]["precision_ci95"] is None
    assert report["overall"]["recall"] == 0
    assert report["overall"]["conditional_accuracy"] is None
    assert report["known_cost_usd"] == 0.02 and report["cost_records"] == 1
    assert score(rows, {})["known_cost_usd"] is None


def test_empty_prediction_file_counts_all_cases_as_missing(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    report = score(cases(), load_rows(path))
    assert report["overall"]["errors_or_missing"] == len(cases())
    assert report["overall"]["accuracy"] == 0
    assert report["overall"]["coverage"] == 0
    with pytest.raises(ValueError, match="No labelled cases"):
        score(load_rows(path), {})


@pytest.mark.parametrize("prediction", [
    {"found": "false"}, {"found": 1}, {"found": False, "error": "timeout"},
    {"found": True, "cost_usd": float("nan")}, {"found": True, "latency_s": -1},
    {"found": True, "cost_usd": True}, {"error": []},
])
def test_malformed_predictions_do_not_produce_accuracy(prediction):
    with pytest.raises(ValueError):
        score(cases(), {"tp": prediction})


def test_duplicates_unknown_ids_and_invalid_gold_are_rejected(tmp_path):
    path = tmp_path / "duplicates.jsonl"
    path.write_text('{"id":"a"}\n{"id":"a"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_rows(path)
    with pytest.raises(ValueError, match="unknown"):
        score(cases(), {"unseen": {"found": False}})
    rows = cases()
    rows["tp"]["expected"] = "true"
    with pytest.raises(ValueError, match="boolean"):
        score(rows, {})


def test_small_perfect_sample_does_not_establish_ninety_percent_lower_bound():
    rows = cases()
    for row in rows.values():
        row.update(label_source="human", split="holdout")
    report = score(rows, {key: {"found": row["expected"]} for key, row in rows.items()})
    assert report["human_holdout_meets_target"]
    assert not report["human_holdout_lower_bounds_meet_target"]
    assert report["human_holdout_only"]


def test_easy_development_examples_cannot_hide_bad_human_holdout():
    rows = {str(index): {"id": str(index), "expected": True, "brand_name": "SyntheticBrand",
                        "category": "text", "provider": "synthetic", "split": "dev" if index < 90 else "holdout",
                        "label_source": "synthetic" if index < 90 else "human"}
            for index in range(100)}
    report = score(rows, {str(index): {"found": index < 90} for index in range(100)})
    assert report["all_cases_meet_numeric_target"]
    assert not report["human_holdout_meets_target"]
    assert report["human_holdout"]["accuracy"] == 0


@pytest.mark.parametrize("overwrite", ["cases", "predictions"])
def test_cli_never_overwrites_inputs(tmp_path, overwrite):
    case_file = tmp_path / "cases.jsonl"
    prediction_file = tmp_path / "predictions.jsonl"
    case_file.write_text("\n".join(json.dumps(row) for row in cases().values()), encoding="utf-8")
    prediction_file.write_text('{"id":"tp","found":true}\n', encoding="utf-8")
    before = {path: path.read_bytes() for path in (case_file, prediction_file)}
    target = case_file if overwrite == "cases" else prediction_file
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts" / "evaluate_brand_detection.py"),
                             "--cases", str(case_file), "--predictions", str(prediction_file), "--output", str(target)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0 and "must not replace" in result.stderr
    assert all(path.read_bytes() == content for path, content in before.items())


def test_cli_scores_fixture_without_api_or_credentials(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests" / "fixtures" / "brand_detection_cases.jsonl"
    rows = load_rows(fixture)
    assert len(rows) >= 24 and all(row["label_source"] == "synthetic" for row in rows.values())
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text("\n".join(json.dumps({"id": key, "found": row["expected"]}) for key, row in rows.items()), encoding="utf-8")
    process = subprocess.run([sys.executable, str(root / "scripts" / "evaluate_brand_detection.py"),
                              "--cases", str(fixture), "--predictions", str(predictions)],
                             capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)[0]
    assert result["overall"]["total"] == len(rows)
    assert result["overall"]["accuracy"] == 1
    assert not result["human_holdout_only"]
