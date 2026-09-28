import runpy
import sys
from pathlib import Path


def test_installer_uses_stable_user_data_and_portable_keeps_its_data(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    config_file = Path(__file__).resolve().parents[1] / "app" / "config.py"
    portable = tmp_path / "portable"
    portable.mkdir()
    monkeypatch.setattr(sys, "executable", str(portable / "AI-Mentions.exe"))
    config = runpy.run_path(str(config_file))
    assert config["PORTABLE"]
    assert config["DATA_DIR"] == portable / "data"

    for name in ("installed", "updated-install-directory"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "installed-mode.txt").touch()
        monkeypatch.setattr(sys, "executable", str(folder / "AI-Mentions.exe"))
        config = runpy.run_path(str(config_file))
        assert not config["PORTABLE"]
        assert config["DATA_DIR"] == tmp_path / "user" / "AIParser"
        assert not (folder / "data").exists()
