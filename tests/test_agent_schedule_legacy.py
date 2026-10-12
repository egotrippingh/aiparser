"""Retired desktop schedule checks, run manually outside server delivery CI."""
from datetime import datetime

from app.agent import schedule_due


def test_legacy_month_days_and_start_time():
    preferences = {"enabled": True, "local_time": "14:30", "month_days": [1, 15, 31]}
    assert not schedule_due(preferences, datetime(2026, 4, 15, 14, 29))
    assert schedule_due(preferences, datetime(2026, 4, 15, 14, 30))
    assert not schedule_due(preferences, datetime(2026, 4, 16, 14, 30))
    assert not schedule_due({**preferences, "month_days": [31]}, datetime(2026, 4, 30, 15))
