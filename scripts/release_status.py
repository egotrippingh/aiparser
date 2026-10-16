"""Read-only release summary: local Git, GitHub delivery and public readiness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import URLError
from urllib.request import urlopen


REPOSITORY = "egotrippingh/aiparser"
READY_URL = "https://airate.tech/api/v1/ready"
SHA = re.compile(r"[0-9a-f]{40}")


class Unavailable(RuntimeError):
    pass


def command(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        result = subprocess.run(
            args, cwd=root, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unavailable(f"{args[0]} missing or timed out") from exc
    if result.returncode:
        raise Unavailable(f"{args[0]} exited {result.returncode}; check access/authentication")
    return result.stdout.strip()


def github(root: Path, *args: str) -> list:
    try:
        data = json.loads(command(root, "gh", *args, "--repo", REPOSITORY))
    except json.JSONDecodeError as exc:
        raise Unavailable("GitHub returned invalid JSON") from exc
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise Unavailable("GitHub returned an unexpected response")
    return data


def readiness() -> str:
    try:
        with urlopen(READY_URL, timeout=10) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise Unavailable("readiness response too large")
        data = json.loads(raw)
    except (OSError, URLError, ValueError) as exc:
        raise Unavailable("readiness request failed or returned invalid JSON") from exc
    if (not isinstance(data, dict) or data.get("ok") is not True
            or not isinstance(data.get("release"), str)
            or not SHA.fullmatch(data["release"])):
        raise Unavailable("readiness is not healthy or has no release SHA")
    return data["release"]


def workflow(root: Path, commit: str, *, production: bool = False) -> str:
    args = ["run", "list", "--workflow", "delivery.yml", "--commit", commit,
            "--limit", "1", "--json", "headSha,status,conclusion,url"]
    if production:
        args += ["--branch", "production", "--event", "push"]
    runs = github(root, *args)
    if not runs:
        raise Unavailable("no delivery run found for this SHA")
    run = runs[0]
    if run.get("headSha") != commit or not isinstance(run.get("url"), str):
        raise Unavailable("delivery run does not identify the requested SHA")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise Unavailable(f"delivery {run.get('status')}/{run.get('conclusion')}; {run['url']}")
    return f"PASS {run['url']}"


def graph_status(root: Path, branch: str, commit: str, dirty: bool) -> str:
    folder = root / "graphify-out"
    if not (folder / "graph.json").is_file():
        return "absent; use rg or refresh when needed"
    try:
        source = (folder / "source-commit.txt").read_text(encoding="utf-8-sig").strip()
        source_branch = (folder / "source-branch.txt").read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return "unverified: source branch/SHA marker missing"
    if not SHA.fullmatch(source) or not source_branch:
        return "unverified: invalid source marker"
    origin = f"indexed {source_branch}@{source}"
    if source != commit or source_branch != branch:
        return f"{origin}; different checkout, refresh before use"
    if dirty:
        return f"{origin}; working tree changed, freshness unverified"
    return f"{origin}; checkout matches (index is not runtime proof)"


def report(root: Path) -> tuple[list[str], int]:
    branch = command(root, "git", "rev-parse", "--abbrev-ref", "HEAD")
    commit = command(root, "git", "rev-parse", "HEAD")
    dirty = bool(command(root, "git", "status", "--porcelain"))
    lines = [f"Local: {branch}@{commit}; {'dirty' if dirty else 'clean'}"]
    failures = 0
    production = live = None
    try:
        remote = command(root, "git", "ls-remote", "origin", "refs/heads/production")
        fields = remote.split()
        if len(fields) != 2 or fields[1] != "refs/heads/production" or not SHA.fullmatch(fields[0]):
            raise Unavailable("origin did not return a production SHA")
        production = fields[0]
        lines.append(f"Production branch: {production}")
    except Unavailable as exc:
        failures += 1
        lines.append(f"Production branch: UNKNOWN ({exc})")
    for label, operation in (
        ("PR", lambda: github(root, "pr", "list", "--head", branch, "--state", "all",
                              "--limit", "1", "--json", "number,url,state,baseRefName,headRefOid")),
        ("HEAD CI", lambda: workflow(root, commit)),
        ("Production CI/deploy", lambda: workflow(root, production, production=True)
         if production else "UNKNOWN (production SHA unavailable)"),
    ):
        try:
            value = operation()
            if label == "PR":
                value = (f"#{value[0].get('number')} {value[0].get('state')} -> "
                         f"{value[0].get('baseRefName')}; {value[0].get('url')}; "
                         f"{'HEAD matches' if value[0].get('headRefOid') == commit else 'HEAD differs'}"
                         if value else "none for this branch")
            lines.append(f"{label}: {value}")
        except Unavailable as exc:
            failures += 1
            lines.append(f"{label}: UNKNOWN/NOT PASS ({exc})")
    try:
        live = readiness()
        matches = live == production
        lines.append(f"Live readiness: {live}; {'MATCH' if matches else 'production match UNCONFIRMED'}")
        if not matches:
            failures += 1
    except Unavailable as exc:
        failures += 1
        lines.append(f"Live readiness: UNKNOWN ({exc})")
    state = "served by production" if live == commit == production else "not confirmed deployed"
    lines += [f"Local HEAD: {state}", f"Graphify: {graph_status(root, branch, commit, dirty)}",
              "Scope: readiness/SHA and workflow only; assets, signed-in flows and backup contents not rechecked."]
    return lines, int(bool(failures))


def main() -> int:
    try:
        lines, status = report(Path(__file__).resolve().parents[1])
    except Unavailable as exc:
        print(f"Release status unavailable: {exc}")
        return 1
    print("\n".join(lines))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
