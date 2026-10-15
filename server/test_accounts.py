"""Seed proof-of-email for unrelated account fixtures without real SMTP."""
from datetime import timedelta

from server.models import EmailRegistration, utcnow
from server.security import new_token, token_hash


def register_account(client, *, json, **kwargs):
    ticket, code = new_token(), "012345"
    with client.app.state.payment_sessions() as db:
        db.add(EmailRegistration(token_hash=token_hash(ticket), email=json["email"].strip().lower(),
            code_hash=token_hash(ticket + ":" + code), expires_at=utcnow() + timedelta(minutes=10)))
        db.commit()
    return client.post("/api/v1/auth/register", json={**json, "ticket": ticket, "code": code}, **kwargs)
