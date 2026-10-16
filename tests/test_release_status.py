import json
import subprocess

import pytest

from scripts import release_status as status


HEAD = "a" * 40
PRODUCTION = "b" * 40


@pytest.fixture
def release(monkeypatch):
    def command(root, *args):
        if args[:3] == ("git", "rev-parse", "--abbrev-ref"):
            return "codex/example"
        if args[:2] == ("git", "rev-parse"):
            return HEAD
        if args[:2] == ("git", "status"):
            return ""
        if args[:2] == ("git", "ls-remote"):
            return f"{PRODUCTION}\trefs/heads/production"
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([{"number":7, "state":"OPEN", "baseRefName":"production",
                                "headRefOid":HEAD, "url":"https://github.com/example/pull/7"}])
        if args[:3] == ("gh", "run", "list"):
            commit = args[args.index("--commit") + 1]
            if commit == PRODUCTION:
                assert "--branch" in args and "--event" in args
            return json.dumps([{"headSha":commit, "status":"completed", "conclusion":"success",
                                "url":"https://github.com/example/actions/runs/1"}])
        raise AssertionError(args)
    monkeypatch.setattr(status, "command", command)
    monkeypatch.setattr(status, "readiness", lambda: PRODUCTION)
    return command


def test_prepared_head_is_not_deployed_even_with_green_ci(tmp_path, release):
    lines, code = status.report(tmp_path)
    assert code == 0
    assert "Local HEAD: not confirmed deployed" in lines
    assert any("Live readiness:" in line and "MATCH" in line for line in lines)
    assert any("PR: #7 OPEN -> production" in line for line in lines)


@pytest.mark.parametrize("conclusion,run_state", [("failure", "completed"), (None, "in_progress"),
                                                   ("cancelled", "completed"), ("skipped", "completed")])
def test_pending_or_failed_run_is_never_pass(tmp_path, release, monkeypatch, conclusion, run_state):
    monkeypatch.setattr(status, "github", lambda *args: [
        {"headSha":HEAD, "status":run_state, "conclusion":conclusion, "url":"https://example.invalid/run"}])
    with pytest.raises(status.Unavailable):
        status.workflow(tmp_path, HEAD)


def test_no_gh_access_still_reports_live_and_exits_nonzero(tmp_path, release, monkeypatch):
    def command(root, *args):
        if args[0] == "gh":
            raise status.Unavailable("gh not authenticated")
        return release(root, *args)
    monkeypatch.setattr(status, "command", command)
    lines, code = status.report(tmp_path)
    assert code == 1
    assert any("HEAD CI: UNKNOWN" in line for line in lines)
    assert any("Live readiness:" in line and "MATCH" in line for line in lines)


def test_live_mismatch_fails_without_claiming_deployment(tmp_path, release, monkeypatch):
    monkeypatch.setattr(status, "readiness", lambda: HEAD)
    lines, code = status.report(tmp_path)
    assert code == 1
    assert "Local HEAD: not confirmed deployed" in lines
    assert any("production match UNCONFIRMED" in line for line in lines)


@pytest.mark.parametrize("runs", [[], [{"headSha":HEAD, "status":"completed", "conclusion":"success",
                                     "url":"https://example.invalid/run"}]], ids=["absent", "wrong-sha"])
def test_missing_or_wrong_sha_run_is_not_pass(tmp_path, monkeypatch, runs):
    monkeypatch.setattr(status, "github", lambda *args: runs)
    with pytest.raises(status.Unavailable):
        status.workflow(tmp_path, PRODUCTION, production=True)


def test_readiness_success_and_network_failure(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            return json.dumps({"ok":True, "release":PRODUCTION}).encode()
    monkeypatch.setattr(status, "urlopen", lambda url, timeout: Response())
    assert status.readiness() == PRODUCTION
    def fail(url, timeout):
        raise TimeoutError("PRIVATE")
    monkeypatch.setattr(status, "urlopen", fail)
    with pytest.raises(status.Unavailable) as exc:
        status.readiness()
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.parametrize("payload", [b'{"ok":false,"release":"'+PRODUCTION.encode()+b'"}',
                                      b'{"ok":true,"release":"local"}', b'[]', b'broken', b'x'*65537],
                         ids=["unhealthy", "no-sha", "wrong-shape", "invalid-json", "oversized"])
def test_invalid_readiness_is_not_success(monkeypatch, payload):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            assert size == 65537
            return payload
    monkeypatch.setattr(status, "urlopen", lambda url, timeout: Response())
    with pytest.raises(status.Unavailable):
        status.readiness()


def test_graph_requires_matching_branch_sha_and_clean_tree(tmp_path):
    folder = tmp_path / "graphify-out"
    folder.mkdir()
    (folder / "graph.json").write_text("{}")
    assert "marker missing" in status.graph_status(tmp_path, "production", HEAD, False)
    (folder / "source-commit.txt").write_text(HEAD)
    (folder / "source-branch.txt").write_text("production")
    assert "checkout matches" in status.graph_status(tmp_path, "production", HEAD, False)
    assert "freshness unverified" in status.graph_status(tmp_path, "production", HEAD, True)
    assert "different checkout" in status.graph_status(tmp_path, "main", HEAD, False)
    assert "different checkout" in status.graph_status(tmp_path, "production", PRODUCTION, False)


def test_subprocess_timeout_is_reported_without_leaking_output(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 20
        assert "shell" not in kwargs
        raise subprocess.TimeoutExpired(args[0], 20, output="PRIVATE")
    monkeypatch.setattr(status.subprocess, "run", timeout)
    with pytest.raises(status.Unavailable, match="timed out") as exc:
        status.command(tmp_path, "gh", "pr", "list")
    assert "PRIVATE" not in str(exc.value)
