"""Alice must not reject a session when an old hidden auth marker remains in DOM."""
import asyncio

from app.scanner.adapters import alice as alice_mod
from app.scanner.adapters.alice import AliceAdapter, _S


class Marker:
    def __init__(self, shown):
        self.shown = shown

    async def wait_for(self, **_kwargs):
        if not self.shown:
            raise TimeoutError("hidden")


class Markers:
    def __init__(self):
        self.items = [Marker(False), Marker(True)]

    @property
    def first(self):
        return self.items[0]

    async def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class Page:
    def __init__(self):
        self.markers = Markers()

    async def goto(self, *_args, **_kwargs):
        pass

    def locator(self, selector):
        assert selector == _S["logged_in_marker"]
        return self.markers


def test_visible_later_auth_marker_confirms_alice_session():
    assert asyncio.run(AliceAdapter().ensure_ready(Page())).ok


def test_no_visible_auth_marker_stays_logged_out(monkeypatch):
    now = [0.0]
    async def sleep(seconds): now[0] += seconds
    page = Page()
    page.markers.items = []
    monkeypatch.setattr(alice_mod.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(alice_mod.asyncio, "sleep", sleep)
    state = asyncio.run(AliceAdapter().ensure_ready(page))
    assert not state.ok and state.reason == "auth_required" and now[0] >= 6
