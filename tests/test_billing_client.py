import asyncio

from app import billing, config


def test_client_reuses_requests_and_closes_each_event_loop(monkeypatch):
    made = []
    requests = []

    class Response:
        is_error = False
        def json(self): return {"ok": True}

    class Client:
        def __init__(self, **_kwargs):
            self.closed = False
            made.append(self)
        async def request(self, _method, _url, **kwargs):
            requests.append(kwargs)
            return Response()
        async def aclose(self): self.closed = True

    monkeypatch.setattr(config, "ACCOUNT_URL", "https://account.example")
    monkeypatch.setattr(billing, "token", lambda: "token")
    monkeypatch.setattr(billing.httpx, "AsyncClient", Client)

    async def cycle():
        await billing.start_client()
        assert await billing._request("GET", "/me") == {"ok": True}
        await billing.close_client()

    asyncio.run(cycle())
    asyncio.run(cycle())
    assert len(made) == 2 and all(client.closed for client in made)
    assert [request["headers"]["Authorization"] for request in requests] == ["Bearer token", "Bearer token"]
    assert [request["timeout"] for request in requests] == [20, 20]
