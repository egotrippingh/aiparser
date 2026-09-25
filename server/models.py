"""Серверные таблицы. Деньги всегда хранятся целым числом копеек."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(250))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    wallet: Mapped[Wallet] = relationship(back_populates="user", uselist=False)


class SessionToken(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),
                      UniqueConstraint("provider", "user_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(24))
    subject: Mapped[str] = mapped_column(String(190))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempts"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_verifier: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(12))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginTicket(Base):
    __tablename__ = "login_tickets"

    ticket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviceCode(Base):
    __tablename__ = "device_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    __tablename__ = "password_resets"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthFailure(Base):
    __tablename__ = "auth_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Wallet(Base):
    __tablename__ = "wallets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    balance_kopeks: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped[User] = relationship(back_populates="wallet")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_kopeks: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_kopeks: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    invoice_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    payment_url: Mapped[str | None] = mapped_column(String(500))
    test_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("user_id", "client_check_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    client_check_id: Mapped[str] = mapped_column(String(100))
    price_kopeks: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="reserved")
    result_status: Mapped[str | None] = mapped_column(String(30))
    analysis_json: Mapped[str | None] = mapped_column(Text)
    analysis_model: Mapped[str | None] = mapped_column(String(100))
    analysis_usage_json: Mapped[str | None] = mapped_column(Text)
    analysis_attempts: Mapped[int] = mapped_column(Integer, default=0)
    arbitration_json: Mapped[str | None] = mapped_column(Text)
    arbitration_model: Mapped[str | None] = mapped_column(String(100))
    arbitration_usage_json: Mapped[str | None] = mapped_column(Text)
    arbitration_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Screenshot(Base):
    __tablename__ = "screenshots"

    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), primary_key=True)
    object_key: Mapped[str] = mapped_column(String(240), unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScanPreferences(Base):
    """One account-wide schedule, shared by the website and local agent."""

    __tablename__ = "scan_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    local_time: Mapped[str] = mapped_column(String(5), default="09:00")
    month_days_json: Mapped[str] = mapped_column(Text, default="[1]")
    browser_mode: Mapped[str] = mapped_column(String(12), default="headless")
    services_json: Mapped[str] = mapped_column(Text, default='["perplexity","chatgpt"]')
    speed_profile: Mapped[str] = mapped_column(String(12), default="balanced")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentDevice(Base):
    __tablename__ = "agent_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    local_time_zone: Mapped[str] = mapped_column(String(80), default="")
    active_scan: Mapped[bool] = mapped_column(Boolean, default=False)


class CloudResult(Base):
    """A local scan result mirrored to the account for browser reports."""

    __tablename__ = "cloud_results"
    __table_args__ = (UniqueConstraint("user_id", "device_id", "local_result_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    local_result_id: Mapped[int] = mapped_column(Integer)
    local_project_id: Mapped[int] = mapped_column(Integer)
    project_name: Mapped[str] = mapped_column(String(120))
    brand_name: Mapped[str] = mapped_column(String(120))
    query_text: Mapped[str] = mapped_column(Text)
    group_tag: Mapped[str | None] = mapped_column(String(120))
    service: Mapped[str] = mapped_column(String(40))
    scan_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(24))
    mention_types_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    check_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_session_factory(database_url: str):
    engine = create_engine(database_url, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)
