"""Manual telemetry compatibility check for the retired desktop agent."""
import telemetry


def test_agent_api_telemetry_boundary(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import create_app
    from app import config
    calls = []
    monkeypatch.setattr(telemetry, "init", lambda **kwargs: False)
    monkeypatch.setattr(telemetry, "capture", lambda exc, **kwargs: calls.append((type(exc), kwargs)))
    monkeypatch.setenv("SENTRY_BROWSER_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("AIRATE_RELEASE", "a" * 40)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    monkeypatch.setattr(config, "SENTRY_DSN", "https://public@example.invalid/2")
    app = create_app()

    @app.get("/telemetry-fixture-error")
    def fail():
        raise RuntimeError("SEEDED-SECRET")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/telemetry")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["dsn"].startswith("https://public@example.invalid/")
    assert client.get("/telemetry-fixture-error").status_code == 500
    assert calls[-1][0] is RuntimeError
    assert calls[-1][1]["component"] == "agent"
