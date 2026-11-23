import asyncio
import shutil
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import uvicorn
from mcp import Client, StdioServerParameters

from server.api_keys import PUBLIC_PREFIX
from server.models import ControlProject, Wallet
from server.test_public_api import api_key_secret, issue_key
from server.test_reporting import seed_report


MCP_DIR = Path(__file__).resolve().parents[1] / "integrations" / "mcp"


@asynccontextmanager
async def serve_local(app):
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            app, lifespan="off", log_config=None, access_log=False, timeout_graceful_shutdown=2,
        ))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("Test REST server exited before startup")
                    await asyncio.sleep(0.01)
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            await task


def mcp_client(script, key, *args):
    node = shutil.which("node")
    assert node, "Install Node.js and run npm ci --prefix integrations/mcp"
    params = StdioServerParameters(
        command=node, args=[str(MCP_DIR / script), *args], env={"AIRATE_API_KEY": key},
    )
    return Client(params, mode="legacy")


def test_mcp_covers_public_rest_and_preserves_account_and_scan_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "fake-key")
    cabinet, owner, other, _, historical, _, _ = seed_report(tmp_path)
    owner_key = issue_key(cabinet, owner)["key"]
    other_key = issue_key(cabinet, other)["key"]
    app = cabinet.app
    exercised = set()

    async def record(scope, receive, send):
        await app(scope, receive, send)
        exercised.add((scope["method"].lower(), scope["route"].path))

    async def workflow():
        async with asyncio.timeout(45), serve_local(record) as server_url:
            base_url = server_url + PUBLIC_PREFIX + "/"
            async with mcp_client("test-runner.mjs", owner_key, base_url) as mcp:
                tools = {tool.name: tool for tool in (await mcp.list_tools()).tools}
                assert tools["list_answers"].annotations.read_only_hint
                assert tools["delete_query"].annotations.destructive_hint
                assert not tools["launch_scan"].annotations.read_only_hint

                async def call(tool, **arguments):
                    result = await mcp.call_tool(tool, arguments)
                    assert not result.is_error, result.content
                    return result.structured_content["data"]

                listed = await call("list_projects")
                assert [row["id"] for row in listed] == [historical["id"]]
                answers = {
                    "project_id": historical["id"], "date_from": "2026-09-01", "date_to": "2026-09-03",
                    "service": "chatgpt", "limit": 1,
                }
                page = await call("list_answers", **answers)
                assert page["items"][0]["answer_text"] == "Original answer"
                page = await call("list_answers", **answers, after_id=page["next_after_id"])
                assert page["items"][0]["scan_date"] == "2026-09-03"
                assert page["next_after_id"] is None

                created = await call("create_project", name="MCP", brand_name="Brand", config={"services": ["chatgpt"]})
                project_id = created["id"]
                query = await call("add_query", project_id=project_id, text="Relevant question", active=False)
                assert query["active"] is False
                assert await call("list_queries", project_id=project_id) == [query]
                project = await call("get_project", project_id=project_id)
                updated = await call(
                    "update_project", project_id=project_id, revision=project["revision"], name="Renamed",
                    brand_name=project["brand_name"], config=project["config"], schedule=project["schedule"],
                    queries=[{**query, "active": True}], device_id=project["device_id"],
                )
                assert updated["name"] == "Renamed"
                quote = await call("get_scan_quote", project_id=project_id)
                assert quote["count"] == 1 and quote["total_kopeks"] > 0
                launch = {
                    "project_id": project_id, "request_id": uuid4().hex,
                    **{key: quote[key] for key in ("revision", "provider_state", "free_scans_state")},
                }
                no_balance = await mcp.call_tool("launch_scan", launch)
                assert no_balance.is_error and "HTTP 402" in no_balance.content[0].text
                with app.state.payment_sessions.begin() as db:
                    db.get(Wallet, db.get(ControlProject, project_id).user_id).balance_kopeks = quote["total_kopeks"]
                run = await call("launch_scan", **launch)
                run_id = run["id"]
                assert (await call("launch_scan", **launch))["id"] == run_id
                assert [row["id"] for row in await call("list_runs", project_id=project_id)] == [run_id]
                assert (await call("get_run", project_id=project_id, run_id=run_id))["state"] == "queued"
                assert await call("control_run", project_id=project_id, run_id=run_id, action="stop") == {"ok": True}
                assert (await call("get_run", project_id=project_id, run_id=run_id))["state"] == "cancelled"
                assert await call("delete_query", project_id=project_id, query_id=query["id"]) == {"ok": True}
                assert await call("list_queries", project_id=project_id) == []

            async with mcp_client("test-runner.mjs", other_key, base_url) as other_client:
                denied = await other_client.call_tool("get_project", {"project_id": project_id})
                assert denied.is_error and "HTTP 404" in denied.content[0].text
            async with mcp_client("test-runner.mjs", "invalid-api-key", base_url) as invalid_client:
                invalid = await invalid_client.call_tool("list_projects")
                assert invalid.is_error and "HTTP 401" in invalid.content[0].text
            assert len(tools) == len(exercised)

    asyncio.run(workflow())
    public_operations = {
        (method, path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(PUBLIC_PREFIX + "/")
        for method in operations
    }
    assert exercised == public_operations


@pytest.mark.parametrize(
    "response, error",
    [
        (httpx.Response(302, headers={"Location": "https://another.example/"}), "HTTP 302"),
        (httpx.Response(200, text="<html>"), "expected a JSON response"),
        (httpx.Response(200, content=b"{", headers={"Content-Type": "application/json"}), "invalid JSON"),
        (None, "reuse the same request_id"),
    ],
)
def test_mcp_returns_errors_without_network_retries(response, error):
    calls = []

    async def handle(scope, receive, send):
        calls.append(scope["path"])
        status = response.status_code if response is not None else 200
        headers = response.headers.raw if response is not None else [
            (b"content-type", b"application/json"), (b"content-length", b"99"),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": response.content if response is not None else b"{}"})

    async def run():
        async with asyncio.timeout(25), serve_local(handle) as base_url:
            async with mcp_client("test-runner.mjs", "fake credential", base_url + "/") as mcp:
                invalid = await mcp.call_tool("get_project", {"project_id": "../api-key"})
                assert invalid.is_error and calls == []
                result = await mcp.call_tool("launch_scan", {
                    "project_id": "a" * 32, "request_id": "b" * 32, "revision": 0,
                    "provider_state": "c" * 64, "free_scans_state": "d" * 64,
                })
                assert result.is_error and error in result.content[0].text
                assert "fake credential" not in result.content[0].text
                assert calls == [f"/projects/{'a' * 32}/runs"]

    asyncio.run(run())


def test_stdio_discovers_tools_with_a_legacy_client():
    async def run():
        async with asyncio.timeout(25), mcp_client("cli.mjs", "test-only") as mcp:
            assert mcp.server_info.name == "AIRate"
            assert "list_projects" in {tool.name for tool in (await mcp.list_tools()).tools}

    asyncio.run(run())
