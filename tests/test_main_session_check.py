from app import main
from app.scanner import profiles


def test_saved_cookie_check_reads_each_service_without_browser_or_network(monkeypatch):
    seen = []
    monkeypatch.setattr(profiles, "cookie_auth_state", lambda service: seen.append(service) or {"state": "none"})
    assert main._check_saved_sessions() == {service: "none" for service in profiles.AUTH_COOKIES}
    assert seen == list(profiles.AUTH_COOKIES)
