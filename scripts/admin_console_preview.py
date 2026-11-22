"""Disposable local preview for the admin console (never production DB)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for key in (
    "DATABASE_URL", "COINSO_SECRET_KEY", "COINSO_PROJECT_ID", "OPENROUTER_API_KEY",
    "OPENROUTER_MANAGEMENT_KEY", "SCRAPELESS_API_KEY", "AIPARSER_XMLRIVER_USER",
    "AIPARSER_XMLRIVER_KEY", "S3_SCREENSHOTS_BUCKET", "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY", "YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET", "SMTP_HOST",
):
    os.environ.pop(key, None)

PUBLIC = "http://127.0.0.1:5173"
ADMIN = "http://127.0.0.1:5174"
PASSWORD = "preview-admin-pass-123"

os.environ["APP_ENV"] = "test"
os.environ["PUBLIC_BASE_URL"] = PUBLIC
os.environ["ADMIN_BASE_URL"] = ADMIN
os.environ["ADMIN_ALLOWED_IPS"] = "127.0.0.1,::1"
os.environ["ADMIN_CONSOLE_PASSWORD"] = PASSWORD
os.environ["AIRATE_ADMIN_PREVIEW"] = "1"

import uvicorn
from server.app import create_app
from server.models import User, Wallet, make_session_factory
from server.security import hash_password

work = Path(tempfile.mkdtemp(prefix="airate-admin-preview-"))
db_url = f"sqlite:///{work / 'preview.db'}"
os.environ["DATABASE_URL"] = db_url
app = create_app(database_url=db_url)
_, sessions = make_session_factory(db_url)
with sessions() as db:
    db.add(User(
        id="preview-admin",
        email="admin@preview.local",
        is_admin=True,
        password_hash=hash_password(PASSWORD),
        wallet=Wallet(balance_kopeks=50_000),
    ))
    db.add(User(
        id="preview-user",
        email="user@preview.local",
        is_admin=False,
        password_hash=hash_password(PASSWORD),
        wallet=Wallet(balance_kopeks=1_000),
    ))
    db.commit()

print(json.dumps({
    "cabinet": f"{PUBLIC}/cabinet/",
    "admin": f"{ADMIN}/",
    "login": "admin",
    "password": PASSWORD,
    "db": str(work),
}, ensure_ascii=False), flush=True)
uvicorn.run(app, host="127.0.0.1", port=8757, log_level="info")
