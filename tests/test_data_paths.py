import runpy
import sys
from pathlib import Path
import pytest


def _installed_config(tmp_path, monkeypatch, *, legacy=False, empty_legacy=False, target=False):
    app_folder = tmp_path / "app"
    app_folder.mkdir(parents=True)
    (app_folder / "installed-mode.txt").touch()
    user_root = tmp_path / "user"
    if legacy:
        legacy_profile = app_folder / "data" / "profiles" / "chatgpt"
        legacy_profile.mkdir(parents=True)
        (legacy_profile / "cookies.sqlite").write_bytes(b"legacy")
    elif empty_legacy:
        (app_folder / "data").mkdir()
    if target:
        installed = user_root / "AIParser"
        installed.mkdir(parents=True)
        (installed / "aiparser.db").write_bytes(b"installed")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_folder / "AI-Mentions.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(user_root))
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "app" / "config.py")), app_folder, user_root


def test_installed_first_launch_reuses_legacy_data_beside_same_app_folder(tmp_path, monkeypatch):
    config, app_folder, _ = _installed_config(tmp_path, monkeypatch, legacy=True)
    assert not config["PORTABLE"]
    assert config["DATA_DIR"] == app_folder / "data"


def test_fresh_or_empty_legacy_folder_uses_local_app_data(tmp_path, monkeypatch):
    fresh, _, user = _installed_config(tmp_path / "fresh", monkeypatch)
    empty, _, empty_user = _installed_config(tmp_path / "empty", monkeypatch, empty_legacy=True)
    assert fresh["DATA_DIR"] == user / "AIParser"
    assert empty["DATA_DIR"] == empty_user / "AIParser"


def test_established_installed_data_wins_when_both_locations_have_state(tmp_path, monkeypatch):
    config, _, user = _installed_config(tmp_path, monkeypatch, legacy=True, target=True)
    assert config["DATA_DIR"] == user / "AIParser"


def test_repeated_selection_stays_on_the_same_legacy_data(tmp_path, monkeypatch):
    first, app_folder, _ = _installed_config(tmp_path, monkeypatch, legacy=True)
    second = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app" / "config.py"))
    assert first["DATA_DIR"] == second["DATA_DIR"] == app_folder / "data"


def test_unreadable_installed_state_never_switches_to_legacy(tmp_path, monkeypatch):
    original = Path.is_file
    def inaccessible(path):
        if path.name == "aiparser.db" and path.parent.name == "AIParser":
            raise PermissionError("installed state unavailable")
        return original(path)
    monkeypatch.setattr(Path, "is_file", inaccessible)
    with pytest.raises(PermissionError, match="installed state unavailable"):
        _installed_config(tmp_path, monkeypatch, legacy=True, target=True)
    assert (tmp_path / "user/AIParser/aiparser.db").read_bytes() == b"installed"
    assert (tmp_path / "app/data/profiles/chatgpt/cookies.sqlite").read_bytes() == b"legacy"


def test_unreadable_installed_profiles_without_database_never_switch_to_legacy(tmp_path, monkeypatch):
    installed_profiles = tmp_path / "user/AIParser/profiles"
    (installed_profiles / "chatgpt").mkdir(parents=True)
    (installed_profiles / "chatgpt/cookies.sqlite").write_bytes(b"installed cookies")
    original = Path.iterdir
    def inaccessible(path):
        if path == installed_profiles:
            raise PermissionError("installed profiles unavailable")
        return original(path)
    monkeypatch.setattr(Path, "iterdir", inaccessible)
    with pytest.raises(PermissionError, match="installed profiles unavailable"):
        _installed_config(tmp_path, monkeypatch, legacy=True)
    assert (installed_profiles / "chatgpt/cookies.sqlite").read_bytes() == b"installed cookies"
