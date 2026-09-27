from fastapi.testclient import TestClient
from sqlalchemy import event

from server.app import create_app


def test_readiness_identifies_release_and_reports_database_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('AIRATE_RELEASE', 'tested-release')
    app = create_app(database_url=f"sqlite:///{tmp_path / 'ready.db'}")
    client = TestClient(app)
    assert client.get('/api/v1/ready').json() == {'ok': True, 'release': 'tested-release'}
    # Fail database execution, while leaving liveness available for diagnosis.
    from sqlalchemy.engine import Engine

    def fail(*args):
        raise RuntimeError('database connection lost with sensitive details')

    event.listen(Engine, 'before_cursor_execute', fail)
    try:
        response = client.get('/api/v1/ready')
        assert response.status_code == 503
        assert 'sensitive' not in response.text
        assert client.get('/api/v1/health').status_code == 200
    finally:
        event.remove(Engine, 'before_cursor_execute', fail)
