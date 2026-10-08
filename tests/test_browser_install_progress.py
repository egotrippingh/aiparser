import asyncio
from io import BytesIO

import pytest

from app.api import browser as api
from app.scanner import browser_install as installer


@pytest.mark.parametrize("total", [100, 0])
def test_download_reports_bytes_then_extraction_and_validation(monkeypatch, total):
    events = []
    monkeypatch.setattr(installer, "available_browser", lambda: None)
    monkeypatch.setattr(installer, "browser_executable", lambda: "browser.exe")

    class Fetcher:
        def install(self, replace):
            assert replace
            self.download_file(BytesIO(), "https://example.test/browser.zip")
            assert events[-1][0] == "extracting"

    def webdl(url, *, buffer, progress_callback):
        progress_callback(50, total)
        return buffer

    monkeypatch.setattr(installer.pkgman, "CamoufoxFetcher", Fetcher)
    monkeypatch.setattr(installer.pkgman, "webdl", webdl)
    installer.install_browser(lambda *event: events.append(event))
    assert ("downloading", 50, total) in events
    assert [event[0] for event in events] == [
        "preparing", "downloading", "downloading", "extracting", "verifying", "complete"
    ]


def test_api_progress_is_live_failure_clears_it_and_retry_resets(monkeypatch):
    monkeypatch.setattr(api, "_install_state", {
        "running": False, "done": False, "error": None, "log": [], "progress": None
    })
    monkeypatch.setattr(api, "camoufox_installed", lambda: False)

    async def scenario():
        loop = asyncio.get_running_loop()
        snapshots = []

        def download(*, on_progress):
            for total in (100, 0):
                on_progress("downloading", 50, total)
                # Inspect through the public endpoint while the worker is still busy.
                async def capture():
                    snapshots.append(api.install_log()["progress"])
                asyncio.run_coroutine_threadsafe(capture(), loop).result(timeout=5)
            raise OSError("Connection lost")

        monkeypatch.setattr(api, "install_browser", download)
        await api.install()
        assert (await api.install())["already_running"]
        await api._install_task
        assert snapshots[0]["percent"] == 50
        assert snapshots[1]["percent"] is None
        assert snapshots[1]["total_bytes"] is None
        failed = api.install_log()
        assert failed["error"] == "Connection lost"
        assert failed["progress"] is None and not failed["running"]
        assert not api._install_state["done"]

        def succeed(*, on_progress):
            on_progress("verifying", 0, 0)
            on_progress("complete", 0, 0)
        monkeypatch.setattr(api, "install_browser", succeed)
        await api.install()
        assert api.install_log()["progress"]["stage"] == "preparing"
        assert api.install_log()["error"] is None
        await api._install_task
        assert api.install_log()["progress"]["stage"] == "complete"
        assert api._install_state["done"]

    asyncio.run(scenario())
