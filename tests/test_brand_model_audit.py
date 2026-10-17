from decimal import Decimal
import json

import httpx
import pytest

from scripts.audit_brand_models import (Budget, CANDIDATES, MINIMUM_PREVIOUS, audit_payload,
    load_cases, report, run)


def cases():
    return [{'id': str(i), 'brand_name': 'PrivateBrand', 'answer_text': 'Answer without entities',
             'provider': 'provider-tag', 'project': 'project-tag'} for i in range(300)]


def metadata():
    return {candidate[0]: {'supported_parameters': ['response_format', 'reasoning']} for candidate in CANDIDATES.values()}


def test_cumulative_ceiling_stops_all_posts_even_when_each_request_fits(tmp_path):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request))) as client:
        with pytest.raises(ValueError, match='Whole audit ceiling'):
            run(cases(), client, metadata(), Budget(Decimal('1')), MINIMUM_PREVIOUS, tmp_path / 'out')
    assert calls == [] and not (tmp_path / 'out').exists()


def test_refused_admission_is_never_submitted(tmp_path):
    class RefusingBudget(Budget):
        def admit(self, ceiling):
            if self.reserved:
                return False
            return super().admit(ceiling)
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('No network'))) as client:
        with pytest.raises(ValueError, match='Whole audit ceiling'):
            run(cases(), client, metadata(), RefusingBudget(Decimal('5')), MINIMUM_PREVIOUS, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('prior', ['0', '0.293', 'NaN', 'Infinity', '5.01', '-1'])
def test_previous_experiment_cannot_be_reset(tmp_path, prior):
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('No network'))) as client:
        with pytest.raises(ValueError):
            run(cases(), client, metadata(), Budget(Decimal('5')), Decimal(prior), tmp_path / 'out')


def test_case_validation_is_enforced_at_run_boundary_and_on_load(tmp_path):
    for bad in [cases()[:299], cases() + cases(), [dict(row, expected=True) for row in cases()],
                [dict(row, answer_text=' ') for row in cases()],
                [dict(row, sources=[1]) for row in cases()]]:
        with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('No network'))) as client:
            with pytest.raises(ValueError):
                run(bad, client, metadata(), Budget(Decimal('5')), MINIMUM_PREVIOUS, tmp_path / 'out')
    path = tmp_path / 'cases.jsonl'
    path.write_text('\n'.join(json.dumps(row) for row in cases()), encoding='utf-8-sig')
    assert len(load_cases(path)) == 300


def test_payload_and_existing_output_guards(tmp_path):
    row = dict(cases()[0], query='The original question', cards_text='Brand card evidence',
               aliases=['Brand alias'], domains=['brand.test'])
    for candidate in CANDIDATES.values():
        payload = audit_payload(row, candidate, {})
        encoded = json.dumps(payload)
        assert 'provider-tag' not in encoded and 'project-tag' not in encoded
        assert all(value in encoded for value in ['Brand card evidence', 'Brand alias', 'brand.test', 'The original question'])
        assert payload['max_tokens'] == 1024 and payload['provider']['max_price']['request'] == 0
    out = tmp_path / 'out'
    out.mkdir()
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('No network'))) as client:
        with pytest.raises(FileExistsError):
            run(cases(), client, metadata(), Budget(Decimal('5')), MINIMUM_PREVIOUS, out)


def test_successful_full_mock_audit_retains_failures_costs_and_private_records(tmp_path, capsys):
    output = tmp_path / 'out'
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        planned = json.loads((output / 'manifest.json').read_text())
        assert planned['completed'] is False and planned['expected_requests'] == 600
        assert Decimal(planned['reserved_shared_ceiling_usd']) <= Decimal('5')
        calls.append(payload['model'])
        if len(calls) == 2:
            return httpx.Response(429, json={'error': 'rate limited'})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content':
            '{"found":false,"confidence":0.9,"reasoning":"Private explanation"}'}}],
            'usage': {'cost': 0.001, 'prompt_tokens': 10, 'completion_tokens': 20}})
    budget = Budget(Decimal('5'))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run(cases(), client, metadata(), budget, MINIMUM_PREVIOUS, output, workers=1)
    assert len(calls) == 600 and result['completed'] is True
    summary = result['report']
    assert summary['total_cases'] == 300 and summary['both_decided'] == 299
    assert summary['both_decision_coverage'] == pytest.approx(299 / 300)
    assert summary['agreement_among_both_decided'] == 1
    assert summary['all_attempts']['errors'] == 1 and summary['all_attempts']['missing'] == 0
    assert summary['all_attempts']['known_cost_usd'] == pytest.approx(.599)
    assert summary['all_attempts']['cost_records'] == 599
    assert summary['all_attempts']['unknown_cost_request_ceiling_usd'] > 0
    assert summary['slices']['provider']['provider-tag']['both_decided'] == 299
    assert 'Private explanation' in (output / 'predictions-private.jsonl').read_text()
    assert 'Private' not in capsys.readouterr().out
    assert Decimal(result['reserved_shared_ceiling_usd']) == budget.reserved
    assert Decimal(result['reserved_new_ceiling_usd']) + MINIMUM_PREVIOUS == budget.reserved


def test_report_shows_missing_cases_and_rejects_duplicate_or_contradictory_records():
    rows = [{'id': '0', 'candidate': name, 'found': False, 'cost_usd': .001} for name in CANDIDATES]
    result = report(cases(), rows)
    assert result['total_cases'] == 300 and result['both_decided'] == 1
    assert result['both_decision_coverage'] == pytest.approx(1 / 300)
    assert result['agreement_among_both_decided'] == 1
    assert result['all_attempts']['missing'] == 598
    with pytest.raises(ValueError, match='Duplicate'):
        report(cases(), rows + rows[:1])
    with pytest.raises(ValueError, match='Failed'):
        report(cases(), [dict(rows[0], error='failed')])
    with pytest.raises(ValueError, match='Unknown'):
        report(cases(), [dict(rows[0], id='foreign')])
