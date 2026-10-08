import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.scanner import browser_install as install


@pytest.fixture
def cache(tmp_path, monkeypatch):
    multi = install.multiversion
    monkeypatch.setattr(install.pkgman, "INSTALL_DIR", tmp_path)
    monkeypatch.setattr(multi, "INSTALL_DIR", tmp_path)
    monkeypatch.setattr(multi, "BROWSERS_DIR", tmp_path / "browsers")
    monkeypatch.setattr(multi, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(install.pkgman, "OS_NAME", "win")
    return tmp_path


def version(cache, name, complete=True):
    path = cache / "browsers" / "official" / name
    path.mkdir(parents=True)
    (path / "version.json").write_text(json.dumps({"version": "152.0.4", "build": name}))
    if complete:
        (path / "camoufox.exe").write_bytes(b"browser")
        (path / "properties.json").write_text('[{"property":"locale","type":"str"}]')
    return path


def test_incomplete_newer_version_falls_back_without_deleting(cache):
    good = version(cache, "beta.30")
    broken = version(cache, "beta.31", False)
    install.multiversion.set_active("browsers/official/beta.31")
    assert install.available_browser() == good
    assert install.browser_executable() == str(good / "camoufox.exe")
    assert install.multiversion.get_active_path() == good
    assert broken.exists()


@pytest.mark.parametrize("missing", ["camoufox.exe", "properties.json"])
def test_missing_launch_resource_is_not_installed(cache, missing):
    path = version(cache, "beta.30")
    (path / missing).unlink()
    assert install.available_browser() is None
    with pytest.raises(RuntimeError, match="повреждён"):
        install.browser_executable()


def test_repair_reinstalls_incomplete_download(cache, monkeypatch):
    path = version(cache, "beta.30", False)
    def repair(*, replace):
        assert replace
        (path / "camoufox.exe").write_bytes(b"browser")
        (path / "properties.json").write_text('[{"property":"locale","type":"str"}]')
    fetch = MagicMock(return_value=SimpleNamespace(install=repair))
    monkeypatch.setattr(install.pkgman, "CamoufoxFetcher", fetch)
    install.install_browser()
    assert install.available_browser() == path
    fetch.assert_called_once()


def test_healthy_install_does_not_download(cache, monkeypatch):
    version(cache, "beta.30")
    fetch = MagicMock()
    monkeypatch.setattr(install.pkgman, "CamoufoxFetcher", fetch)
    install.install_browser()
    fetch.assert_not_called()
