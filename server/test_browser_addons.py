"""A fresh PC or interrupted optional addon download must not block AI login."""

import asyncio

import pytest
from camoufox import addons
from camoufox.exceptions import InvalidAddonPath

from app.scanner import browser, browser_install


@pytest.mark.parametrize("partial", [False, True])
def test_login_and_scan_ignore_missing_or_partial_optional_addon(tmp_path, monkeypatch, partial):
    monkeypatch.setattr(addons, "ADDONS_DIR", tmp_path / "addons")
    broken = addons.ADDONS_DIR / "UBO"
    if partial:
        broken.mkdir(parents=True)
        # This is the exact exception seen on the other PC, before the fix.
        with pytest.raises(InvalidAddonPath, match="manifest.json is missing"):
            addons.confirm_paths([str(broken)])

    def unexpected_download(*args, **kwargs):
        pytest.fail("Login must not download an optional ad blocker")

    monkeypatch.setattr(addons, "download_and_extract", unexpected_download)
    monkeypatch.setattr(browser, "camoufox_installed", lambda: True)
    monkeypatch.setattr(browser_install, "browser_executable", lambda: "browser.exe")
    monkeypatch.setattr(browser.config, "profile_dir", lambda _: tmp_path / "profile")
    modes = []

    class Launch:
        def __init__(self, **options):
            paths = []
            # Exercise upstream's real default addon selection and validation.
            addons.add_default_addons(paths, options.get("exclude_addons"))
            addons.confirm_paths(paths)
            assert paths == []
            modes.append(options["headless"])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(browser, "AsyncCamoufox", Launch)
    monkeypatch.setattr(browser, "_geoip_works", False)

    async def run():
        for headless in (False, True):
            async with browser.service_context("chatgpt", headless=headless):
                pass

    asyncio.run(run())
    assert modes == [False, True]
    assert broken.exists() == partial  # Existing caches were not deleted/replaced.
