"""Reserved legacy JSON recovers within the original budget; settled history is immutable."""
import json

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server.ai import AIResult, OpenRouterAI
from server.checks import analyze_check, arbitrate_check, complete_check
from server.models import Base, Check, LedgerEntry, User, Wallet


@pytest.fixture
def state():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(id='owner', email='owner@example.test', password_hash='unused')
        db.add_all([user, Wallet(user_id=user.id, balance_kopeks=1000),
            Check(user_id=user.id, client_check_id='probe', price_kopeks=120,
                  analysis_json='{"found":true,"confidence":"0.9"}', analysis_attempts=1,
                  analysis_usage_json='{"cost":0.01}')])
        db.commit()
        yield db, user, db.scalar(select(Check))
    engine.dispose()


class AI:
    model = 'primary'
    arbiter_model = 'arbiter'
    calls = 0
    def analyze(self, *_args):
        self.calls += 1
        return AIResult('{"found":false,"confidence":0.9}', self.model, {'cost': 0.02})
    arbitrate = analyze


@pytest.mark.parametrize('stage', ['analysis', 'arbitration'])
def test_invalid_reserved_cache_recovers_without_resetting_budget_or_cost(state, stage):
    db, user, check = state
    ai = AI()
    if stage == 'arbitration':
        check.arbitration_json = check.analysis_json
        check.arbitration_usage_json = check.analysis_usage_json
        check.arbitration_attempts = 1
        check.analysis_json = '{"found":false,"confidence":0.1}'
        db.commit()
    operation = analyze_check if stage == 'analysis' else arbitrate_check
    result = operation(db, user, 'probe', '', [], ai)
    assert json.loads(result['raw'])['found'] is False
    assert getattr(check, stage + '_attempts') == 2
    assert json.loads(getattr(check, stage + '_usage_json'))['cost'] == pytest.approx(0.03)
    assert ai.calls == 1
    assert operation(db, user, 'probe', '', [], ai) == result
    assert ai.calls == 1


def test_exhausted_bad_primary_cache_cannot_charge_an_error(state):
    db, user, check = state
    check.analysis_attempts = 2
    db.commit()
    ai = AI()
    with pytest.raises(HTTPException) as error:
        analyze_check(db, user, 'probe', '', [], ai)
    assert error.value.status_code == 409 and ai.calls == 0
    db.rollback()
    db.refresh(check)
    assert check.analysis_json is None and check.analysis_attempts == 2
    assert complete_check(db, user, 'probe', 'error') == 'released'
    assert db.get(Wallet, user.id).balance_kopeks == 1000
    assert db.scalar(select(LedgerEntry)) is None


def test_settled_legacy_cache_is_replayed_without_reanalysis_or_rewrite(state):
    db, user, check = state
    check.status = 'settled'
    db.commit()
    original = check.analysis_json
    ai = AI()
    assert analyze_check(db, user, 'probe', '', [], ai)['raw'] == original
    assert check.analysis_json == original and check.analysis_attempts == 1 and ai.calls == 0


@pytest.mark.parametrize('digits', [400, 5000])
def test_huge_confidence_consumes_attempts_and_is_bounded(state, monkeypatch, digits):
    db, user, check = state
    check.analysis_json = check.analysis_usage_json = None
    check.analysis_attempts = 0
    db.commit()
    calls = []
    original_client = httpx.Client
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content':
            '{"found":true,"confidence":' + '9' * digits + '}'}}], 'usage': {'cost': 0.01}})
    monkeypatch.setattr('server.ai.httpx.Client', lambda **kwargs:
        original_client(transport=httpx.MockTransport(handler), **kwargs))
    ai = OpenRouterAI('synthetic-key')
    try:
        statuses = []
        for _ in range(6):
            with pytest.raises(HTTPException) as error:
                analyze_check(db, user, 'probe', '', [], ai)
            statuses.append(error.value.status_code)
        assert statuses == [502, 502, 409, 409, 409, 409]
        assert len(calls) == check.analysis_attempts == 2
    finally:
        ai.close()
