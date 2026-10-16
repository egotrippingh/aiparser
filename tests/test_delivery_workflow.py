from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import textwrap


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "delivery.yml"


def _job(name: str) -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z]+:|\Z)", workflow, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(1)


def _bash() -> str:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    return str(git_bash) if git_bash.exists() else shutil.which("bash") or "bash"


def _run(script: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([_bash(), "-c", script], env=environment, text=True, capture_output=True, check=False, timeout=10)


def test_delivery_jobs_share_the_tested_frontend_and_single_image() -> None:
    backend = _job("backend")
    frontend = _job("frontend")
    image = _job("image")
    deploy = _job("deploy")

    assert "needs: frontend" in image
    assert "name: airate-web-${{ github.sha }}" in frontend
    assert "path: web/" in frontend
    assert "if-no-files-found: error" in frontend
    assert "name: airate-web-${{ github.sha }}" in image
    assert "context: ." in image
    assert image.count("docker/build-push-action@") == 1
    assert image.count("docker run --rm") == 1
    assert "name: airate-release-${{ github.sha }}" in image
    assert "release_sha256: ${{ steps.archive.outputs.release_sha256 }}" in image
    assert "python -m pytest tests/test_delivery_workflow.py -q" in backend

    assert "needs: [checks, image]" in deploy
    assert "name: airate-release-${{ github.sha }}" in deploy
    assert "needs.image.outputs.release_sha256" in deploy
    assert "actions/checkout@" not in deploy
    assert "npm " not in deploy
    assert "docker build" not in deploy
    assert "ssh \"${options[@]}\"" in deploy


def test_aggregate_rejects_failed_cancelled_and_skipped_dependencies() -> None:
    checks = _job("checks")
    assert "needs: [backend, frontend, image]" in checks
    assert "if: always()" in checks
    script = textwrap.dedent(re.search(r"run: \|\n(.*)", checks, re.DOTALL).group(1))
    placeholders = ("backend", "frontend", "image")
    environment = os.environ.copy()

    cases = [("success", "success", "success", 0)]
    for index in range(3):
        for status in ("failure", "cancelled", "skipped"):
            statuses = ["success", "success", "success"]
            statuses[index] = status
            cases.append((*statuses, 1))
    for *statuses, expected_returncode in cases:
        rendered = script
        for job, status in zip(placeholders, statuses, strict=True):
            rendered = rendered.replace(f"${{{{ needs.{job}.result }}}}", status)
        result = _run(rendered, environment)
        assert result.returncode == expected_returncode, result.stderr


def test_deploy_checksum_gate_rejects_a_tampered_archive(tmp_path: Path) -> None:
    deploy = _job("deploy")
    script_match = re.search(r"- name: Verify release archive\n.*?run: \|\n(.*?)(?=      - name:|\Z)", deploy, re.DOTALL)
    assert script_match
    archive = tmp_path / "release.tar.gz"
    archive.write_bytes(b"tested image")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    script = textwrap.dedent(script_match.group(1)).replace("${{ needs.image.outputs.release_sha256 }}", checksum)
    environment = os.environ.copy() | {"RUNNER_TEMP": str(tmp_path)}
    if os.name == "nt":
        bash_directory = f"/{str(tmp_path)[0].lower()}{str(tmp_path)[2:].replace(chr(92), '/')}"
        script = script.replace("$RUNNER_TEMP", bash_directory)
    assert _run(script, environment).returncode == 0
    archive.write_bytes(b"tampered image")
    assert _run(script, environment).returncode != 0


def test_delivery_actions_are_pinned_to_verified_revisions() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    actions = re.findall(r"uses: ([^\s]+)", workflow)
    assert actions
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in actions)
