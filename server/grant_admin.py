"""One-time operator command: grant unlimited checks to a verified Yandex account.

Usage: python -m server.grant_admin USER_ID
DATABASE_URL must point to the intended account database.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from sqlalchemy import select

from server.migrate import upgrade_database
from server.models import OAuthIdentity, User, make_session_factory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("user_id", help="Exact ID from the account database")
    parser.add_argument("--env-file", type=Path, help="Local environment file for this server")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    upgrade_database(database_url)
    engine, sessions = make_session_factory(database_url)
    try:
        with sessions.begin() as db:
            user = db.get(User, args.user_id)
            if user is None:
                raise SystemExit("User not found")
            linked = db.scalar(select(OAuthIdentity.id).where(
                OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "yandex"))
            if linked is None:
                raise SystemExit("Yandex identity is required for admin entitlement")
            user.is_admin = True
            print(f"Admin entitlement granted to {user.id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
