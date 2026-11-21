import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from mcp import Client, StdioServerParameters

from integrations.airate_mcp import create_server
from server.api_keys import PUBLIC_PREFIX
from server.models import ControlProject, Wallet
from server.test_public_api import issue_key
from server.test_reporting import seed_report


def test_mcp_covers_public_rest_and_preserves_account_and_scan_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "fake-key")
    cabinet, owner, other, _, historical, _, _ = seed_report(tmp_path)
    headers = {"Authorization": "Bearer " + issue_key(cabinet, owner)["key"]}
    other_key = issue_key(cabinet, other)["key"]
    app = cabinet.app
    exercised = set()

    async def record(scope, receive, send):
        await app(scope, receive, send)
        exercised.add((scope["method"].lower(), scope["route"].path))

    async def workflow():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=record),
            base_url="http://testserver" + PUBLIC_PREFIX + "/",
            headers=headers,
        ) as rest:
            async with Client(create_server(rest)) as mcp:
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

                rest.headers["Authorization"] = "Bearer " + other_key
                denied = await mcp.call_tool("get_project", {"project_id": project_id})
                assert denied.is_error and "HTTP 404" in denied.content[0].text
                rest.headers["Authorization"] = other["Authorization"]
                invalid = await mcp.call_tool("list_projects")
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

    def handle(request):
        calls.append(request.url.path)
        if response is None:
            raise httpx.ReadTimeout("fake credential must not appear in the result", request=request)
        return response

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="https://rest.test/") as rest:
            async with Client(create_server(rest)) as mcp:
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
    script = Path(__file__).resolve().parents[1] / "integrations" / "airate_mcp.py"

    async def run():
        params = StdioServerParameters(command=sys.executable, args=[str(script)], env={"AIRATE_API_KEY": "test-only"})
        async with asyncio.timeout(25), Client(params, mode="legacy") as mcp:
            assert mcp.server_info.name == "AIRate"
            assert "list_projects" in {tool.name for tool in (await mcp.list_tools()).tools}

    asyncio.run(run())
