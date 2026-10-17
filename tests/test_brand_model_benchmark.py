from decimal import Decimal
import json

import httpx
import pytest

from scripts.benchmark_brand_models import Budget, CANDIDATES, call, payload_for, request_ceiling, run


def fixture():
    return {"a": {"id": "a", "expected": True, "brand_name": "TestBrand", "answer_text": "TestBrand makes tools.",
                  "category": "text", "provider": "synthetic", "split": "dev", "label_source": "synthetic"}}


def test_budget_refuses_calls_before_network_and_never_exceeds_five(tmp_path):
    for invalid in ("0", "-1", "NaN", "Infinity", "5.01"):
        with pytest.raises(ValueError):
            Budget(Decimal(invalid))
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200)
    metadata = {CANDIDATES["lite"][0]: {"supported_parameters": ["response_format", "reasoning", "temperature"]}}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run(fixture(), ["lite"], client, metadata, Budget(Decimal("0.0000001")), tmp_path / "out")
    assert calls == []
    assert result["reports"][0]["overall"]["errors_or_missing"] == 1
    assert result["reserved_ceiling_usd"] == "0"


def test_payload_omits_labels_and_uses_provider_price_caps():
    payload = payload_for(fixture()["a"], CANDIDATES["lite"], 3000, {"supported_parameters": []})
    assert "expected" not in json.dumps(payload)
    assert "temperature" not in payload
    assert payload["provider"]["max_price"]["request"] == 0
    assert payload["reasoning"] == {"effort": "minimal", "exclude": True}
    assert request_ceiling(payload) > 0


def test_paid_truncated_response_retains_usage_and_never_becomes_negative():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": ""}}],
                                         "usage": {"cost": 0.002, "completion_tokens": 3000}})
    payload = payload_for(fixture()["a"], CANDIDATES["lite"], 3000, {})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        record = call(client, "a", payload)
    assert record["found"] is None and record["error"] == "truncated"
    assert record["cost_usd"] == 0.002


def test_live_probe_refuses_human_data_and_existing_output_before_calls(tmp_path):
    rows = fixture()
    rows["a"]["label_source"] = "human"
    metadata = {CANDIDATES["lite"][0]: {"supported_parameters": ["response_format"]}}
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("network not allowed"))) as client:
        with pytest.raises(ValueError, match="synthetic"):
            run(rows, ["lite"], client, metadata, Budget(Decimal("5")), tmp_path / "out")
        rows["a"]["label_source"] = "synthetic"
        output = tmp_path / "exists"
        output.mkdir()
        with pytest.raises(FileExistsError):
            run(rows, ["lite"], client, metadata, Budget(Decimal("5")), output)
