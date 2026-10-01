from __future__ import annotations

import telemetry
import asyncio
import gzip
import json
import pytest
import sentry_sdk
from sentry_sdk.envelope import Envelope, Item


@pytest.fixture
def collector(monkeypatch):
    bodies = []
    class RecordingTransport(telemetry._transport_type()):
        def _send_request(self, body, headers, endpoint_type, envelope=None):
            if headers.get("Content-Encoding") == "gzip": body = gzip.decompress(body)
            bodies.append(body)
    client = sentry_sdk.Client(dsn="https://public@example.invalid/1", transport=RecordingTransport,
        before_send=telemetry._before_send, default_integrations=False, send_client_reports=False,
        release="2026.10.1.3", environment="test", send_default_pii=False)
    monkeypatch.setattr(telemetry, "_enabled", True)
    with sentry_sdk.new_scope() as scope:
        scope.set_client(client)
        yield client, bodies
    client.close(timeout=1)


def test_actual_sdk_serialized_envelope_and_expected_errors(collector):
    from app.scanner.adapters.base import CaptchaError, AuthRequiredError, ProviderQuotaError, ServiceUnavailableError
    from app.billing import BillingError
    client, bodies = collector
    with sentry_sdk.new_scope() as scope:
        scope.set_extra("prompt", "SEEDED-SECRET")
        scope.set_user({"email": "SEEDED-SECRET", "ip_address": "SEEDED-SECRET"})
        scope.add_attachment(bytes=b"SEEDED-SECRET", filename="SEEDED-SECRET.txt")
        for error in [CaptchaError("SEEDED-SECRET"), AuthRequiredError("SEEDED-SECRET"), ProviderQuotaError("SEEDED-SECRET"), BillingError("SEEDED-SECRET", 401), asyncio.CancelledError()]:
            # Global SDK hooks bypass telemetry.capture; before_send must filter too.
            sentry_sdk.capture_exception(error)
        code = compile('raise RuntimeError("SEEDED-SECRET captcha")', "app/control_agent.py", "exec")
        try: exec(code)
        except RuntimeError as error:
            telemetry.capture(error, component="agent", operation="control_sync", user_id="a" * 32, run_id="b" * 32)
        telemetry.capture(ServiceUnavailableError("SEEDED-SECRET"), component="agent", operation="scan_query")
    client.flush(timeout=2)
    assert len(bodies) == 2
    for body in bodies:
        assert b"SEEDED-SECRET" not in body
        lines = body.splitlines()
        assert len(lines) == 3
        assert json.loads(lines[1])["type"] == "event"
        assert set(json.loads(lines[0])) <= {"event_id"}
    event = json.loads(bodies[0].splitlines()[2])
    assert event["user"] == {"id": "a" * 32}
    assert event["contexts"] == {"run": {"id": "b" * 32}}
    assert event["exception"]["values"][0]["stacktrace"]["frames"] == [{"filename": "app/control_agent.py", "lineno": 1}]
    assert event["release"] == "2026.10.1.3"


def test_transport_drops_late_sdk_items_and_metadata(collector):
    client, bodies = collector
    envelope = Envelope(headers={"trace": {"transaction": "SEEDED-SECRET"}})
    envelope.add_event({"event_id": "c" * 32, "exception": {"values": [{"type": "SEEDED-SECRET", "value": "SEEDED-SECRET", "stacktrace": {"frames": [{"filename": "app/private/../SEEDED-SECRET.py", "lineno": 1, "vars": {"password": "SEEDED-SECRET"}}]}}]}, "tags": {"operation": "SEEDED-SECRET"}, "sdk": {"name": "SEEDED-SECRET"}, "server_name": "SEEDED-SECRET"})
    envelope.items.append(Item(b"SEEDED-SECRET", type="attachment", filename="SEEDED-SECRET"))
    envelope.items.append(Item(b"SEEDED-SECRET", type="session"))
    client.transport.capture_envelope(envelope)
    client.transport.capture_envelope(Envelope(items=[Item(b"SEEDED-SECRET", type="client_report")]))
    client.flush(timeout=2)
    assert len(bodies) == 1
    assert b"SEEDED-SECRET" not in bodies[0]
    assert len(bodies[0].splitlines()) == 3


def test_capture_identity_isolation_and_collector_failure(collector, monkeypatch):
    client, bodies = collector
    async def worker(user):
        await asyncio.sleep(0)
        telemetry.capture(RuntimeError("secret"), component="agent", operation="control_sync", user_id=user)
    async def run(): await asyncio.gather(worker("a" * 32), worker("b" * 32), worker(None))
    with sentry_sdk.isolation_scope() as scope:
        scope.set_user({"id": "c" * 32})
        scope.set_context("run", {"id": "d" * 32})
        asyncio.run(run())
    client.flush(timeout=2)
    events = [json.loads(body.splitlines()[2]) for body in bodies]
    assert [event.get("user") for event in events] == [{"id": "a" * 32}, {"id": "b" * 32}, None]
    assert all("contexts" not in event for event in events)
    def fail(*args, **kwargs): raise OSError("collector unavailable")
    monkeypatch.setattr(client.transport, "_send_request", fail)
    telemetry.capture(RuntimeError("real failure"), component="agent", operation="control_sync")
    telemetry.flush()  # background collector failure cannot reach caller


def test_private_absolute_paths_do_not_become_module_frames(collector):
    client, bodies = collector
    code = compile('raise RuntimeError("secret")', "C:/Users/app/PRIVATE-SENTINEL/project/app/scanner/orchestrator.py", "exec")
    try: exec(code)
    except RuntimeError as error: telemetry.capture(error, component="agent", operation="scan_query")
    client.flush(timeout=2)
    assert len(bodies) == 1
    assert b"PRIVATE-SENTINEL" not in bodies[0]
    assert json.loads(bodies[0].splitlines()[2])["exception"]["values"][0]["stacktrace"]["frames"] == []


def test_unreadable_sidecar_does_not_break_startup(tmp_path, monkeypatch):
    # Execute the real config module without reading existing user data.
    import runpy
    from pathlib import Path
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "AI-Mentions.exe"))
    monkeypatch.delenv("AIPARSER_SENTRY_DSN", raising=False)
    (tmp_path / "sentry-dsn.txt").write_bytes(b"\xff\xfe\xff")
    values = runpy.run_path(str(Path(__file__).parents[1] / "app" / "config.py"))
    assert values["SENTRY_DSN"] == ""


def test_real_api_boundaries_and_public_runtime_config(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import create_app
    from app.api import create_app as agent_app
    from app import config
    calls = []
    monkeypatch.setattr(telemetry, "init", lambda **kwargs: False)
    monkeypatch.setattr(telemetry, "capture", lambda exc, **kwargs: calls.append((type(exc), kwargs)))
    monkeypatch.setenv("SENTRY_BROWSER_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("AIRATE_RELEASE", "a" * 40)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    monkeypatch.setattr(config, "SENTRY_DSN", "https://public@example.invalid/2")
    for app, component in [(create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}"), "server"), (agent_app(), "agent")]:
        @app.get("/telemetry-fixture-error")
        def fail(): raise RuntimeError("SEEDED-SECRET")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/telemetry")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["dsn"].startswith("https://public@example.invalid/")
        assert client.get("/telemetry-fixture-error").status_code == 500
        assert calls[-1][0] is RuntimeError
        assert calls[-1][1]["component"] == component
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError): create_app()
    assert calls[-1][1]["operation"] == "startup"


def test_sanitized_event_excludes_seeded_secret_and_paths():
    try:
        raise RuntimeError("seeded-secret query=do-not-send")
    except RuntimeError as exc:
        event = telemetry._before_send({"event_id": "a" * 32, "release": "2026.10.1.3", "environment": "test",
                                        "tags": {"component": "agent", "operation": "scan_query", "bad": "seeded-secret"},
                                        "extra": {"query": "seeded-secret"}, "user": {"id": "bad"}},
                                       {"exc_info": (type(exc), exc, exc.__traceback__)})
    assert event and "seeded-secret" not in repr(event)
    assert event["exception"]["values"][0]["type"] == "RuntimeError"
    assert event["tags"] == {"component": "agent", "operation": "scan_query"}


def test_invalid_dsn_is_disabled():
    assert telemetry.init(component="agent", dsn="not-a-dsn") is False
