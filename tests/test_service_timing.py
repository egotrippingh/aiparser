"""Frozen per-service timing reaches adapter asks and inter-query pauses."""
import asyncio
from contextlib import asynccontextmanager

from app.scanner import humanize, orchestrator
from app.scanner.adapters.base import ReadyState


class Page:
    def is_closed(self): return False


class Context:
    pages = [Page()]
    async def new_page(self): return Page()


class Adapter:
    async def ensure_ready(self, page): return ReadyState(ok=True)


async def _routed(monkeypatch, service, settings, floor=(0.0, 0.0)):
    speeds, pauses = [], []
    adapter = Adapter()
    adapter.min_delay_sec = floor

    @asynccontextmanager
    async def context(*_args, **_kwargs):
        yield Context()
    async def run_one(_project, _query, _service, _adapter, _page, _settings, speed, *_args):
        speeds.append(speed)
        return "found"
    async def between(_idx, *, lo, hi, break_every):
        pauses.append((lo, hi, break_every))

    monkeypatch.setattr(orchestrator, "get_adapter", lambda _: adapter)
    monkeypatch.setattr(orchestrator, "service_context", context)
    monkeypatch.setattr(orchestrator, "_record_auth_state", lambda *_: None)
    monkeypatch.setattr(orchestrator, "_run_one", run_one)
    monkeypatch.setattr(orchestrator.humanize, "between_queries", between)
    ctl = orchestrator.ScanController(1, 1, total=3, scan_date="2026-10-01")
    await orchestrator._run_service({"id": 1}, service, [{"id": n} for n in range(3)],
                                    settings, "", "", "never", ctl)
    return speeds, pauses


def test_fast_profiles_are_service_specific_and_copied():
    assert humanize.profile("careful") == humanize.PROFILES["careful"]
    assert humanize.profile("balanced") == humanize.PROFILES["balanced"]
    assert humanize.profile("fast", "perplexity") == humanize.PROFILES["fast"]
    alice = humanize.profile("fast", "alice")
    alice["typing"] = 99
    assert humanize.profile("fast", "alice")["typing"] == 0.2


def test_snapshot_freezes_tuned_values_and_chatgpt_floor(monkeypatch):
    monkeypatch.setattr(orchestrator.repo, "all_settings", lambda: {"speed_profile": "fast"})
    monkeypatch.setattr(orchestrator, "get_adapter", orchestrator.ADAPTERS.__getitem__)
    snapshot = orchestrator._settings_snapshot(["alice", "google_aio", "chatgpt", "perplexity"])
    timing = snapshot["per_service_timing"]
    assert timing["alice"] == {"delay_min_sec": 1.0, "delay_max_sec": 2.0, "break_every_n": 0, "typing_speed": 0.2}
    assert timing["google_aio"] == timing["alice"]
    assert timing["chatgpt"]["typing_speed"] == 0.2
    assert (timing["chatgpt"]["delay_min_sec"], timing["chatgpt"]["delay_max_sec"]) == (10.0, 15.0)
    assert timing["perplexity"] == {"delay_min_sec": 2.0, "delay_max_sec": 5.0, "break_every_n": 0, "typing_speed": 0.4}
    monkeypatch.setitem(humanize.PROFILES["fast"], "typing", 9.0)
    assert timing["alice"]["typing_speed"] == 0.2


def test_routed_service_uses_frozen_timing_and_legacy_fallback(monkeypatch):
    frozen = {"headless": False, "per_service_timing": {
        "alice": {"typing_speed": 0.2, "delay_min_sec": 1.0, "delay_max_sec": 2.0, "break_every_n": 7},
        "google_aio": {"typing_speed": 0.2, "delay_min_sec": 1.0, "delay_max_sec": 2.0, "break_every_n": 0},
        "chatgpt": {"typing_speed": 0.2, "delay_min_sec": 10.0, "delay_max_sec": 15.0, "break_every_n": 0},
        "perplexity": {"typing_speed": 0.4, "delay_min_sec": 2.0, "delay_max_sec": 5.0, "break_every_n": 0},
    }}
    speeds, pauses = asyncio.run(_routed(monkeypatch, "alice", frozen))
    assert speeds == [0.2] * 3 and pauses == [(1.0, 2.0, 7)] * 2
    speeds, pauses = asyncio.run(_routed(monkeypatch, "google_aio", frozen))
    assert speeds == [0.2] * 3 and pauses == [(1.0, 2.0, 0)] * 2
    speeds, pauses = asyncio.run(_routed(monkeypatch, "chatgpt", frozen, floor=(99.0, 99.0)))
    assert speeds == [0.2] * 3 and pauses == [(10.0, 15.0, 0)] * 2
    speeds, pauses = asyncio.run(_routed(monkeypatch, "perplexity", frozen))
    assert speeds == [0.4] * 3 and pauses == [(2.0, 5.0, 0)] * 2
    legacy = {"headless": False, "typing_speed": 0.4, "delay_min_sec": 2.0,
              "delay_max_sec": 5.0, "break_every_n": 3}
    speeds, pauses = asyncio.run(_routed(monkeypatch, "chatgpt", legacy, floor=(10.0, 15.0)))
    assert speeds == [0.4] * 3 and pauses == [(10.0, 15.0, 3)] * 2
