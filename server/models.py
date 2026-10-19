"""Серверные таблицы. Деньги всегда хранятся целым числом копеек."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, text
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
    connect_id: Mapped[str | None] = mapped_column(String(32))
    parent_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginTicket(Base):
    __tablename__ = "login_tickets"

    ticket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class YandexRegistration(Base):
    __tablename__ = "yandex_registrations"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(190))
    subject: Mapped[str] = mapped_column(String(190))
    connect_id: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailRegistration(Base):
    __tablename__ = "email_registrations"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(190), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviceCode(Base):
    __tablename__ = "device_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BrowserLoginTicket(Base):
    __tablename__ = "browser_login_tickets"
    ticket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_hash: Mapped[str] = mapped_column(String(64), index=True)
    destination: Mapped[str] = mapped_column(String(16))
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


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (CheckConstraint("max_redemptions IS NULL OR max_redemptions > 0", name="ck_promo_max_redemptions"),)

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    scans_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("promo_codes.code"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FreeScanBalance(Base):
    __tablename__ = "free_scan_balances"
    __table_args__ = (CheckConstraint("remaining >= 0", name="ck_free_scan_remaining"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    service: Mapped[str] = mapped_column(String(40), primary_key=True)
    remaining: Mapped[int] = mapped_column(Integer, default=0)


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


class TopupEmail(Base):
    __tablename__ = "topup_emails"
    __table_args__ = (Index("ix_topup_emails_due", "status", "next_attempt_at"),)

    order_id: Mapped[str] = mapped_column(ForeignKey("payment_orders.id"), primary_key=True)
    email: Mapped[str] = mapped_column(String(190))
    amount_kopeks: Mapped[int] = mapped_column(Integer)
    balance_kopeks: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("user_id", "client_check_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    client_check_id: Mapped[str] = mapped_column(String(100))
    price_kopeks: Mapped[int] = mapped_column(Integer)
    free_scan_service: Mapped[str | None] = mapped_column(String(40))
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


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (CheckConstraint("role IN ('editor', 'viewer')", name="ck_project_member_role"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("control_projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(12))
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
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    capabilities_json: Mapped[str] = mapped_column(Text, default="{}")


class CloudResult(Base):
    """A local scan result mirrored to the account for browser reports."""

    __tablename__ = "cloud_results"
    __table_args__ = (UniqueConstraint("user_id", "device_id", "local_result_id"),
        Index("uq_cloud_server_result", "run_id", "query_id", "service", unique=True,
              sqlite_where=text("device_id IS NULL AND run_id IS NOT NULL"),
              postgresql_where=text("device_id IS NULL AND run_id IS NOT NULL")))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(64))
    local_result_id: Mapped[int | None] = mapped_column(Integer)
    local_project_id: Mapped[int | None] = mapped_column(Integer)
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
    error_message: Mapped[str | None] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    check_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    query_id: Mapped[str | None] = mapped_column(String(32))
    run_id: Mapped[str | None] = mapped_column(String(32), index=True)


class ControlProject(Base):
    __tablename__ = "control_projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    brand_name: Mapped[str] = mapped_column(String(120))
    device_id: Mapped[str | None] = mapped_column(String(64))
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    queries_json: Mapped[str] = mapped_column(Text, default="[]")
    schedule_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ControlRun(Base):
    __tablename__ = "control_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("control_projects.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(64))
    phase: Mapped[str] = mapped_column(String(16), default="agent", server_default="agent")
    state: Mapped[str] = mapped_column(String(24), default="queued")
    desired_state: Mapped[str] = mapped_column(String(24), default="running")
    # Nullable unique keys serialize projects and execution on each device.
    active_project_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    active_device_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    request_key: Mapped[str] = mapped_column(String(160), unique=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    progress_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(String(1000))
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ServerCapture(Base):
    """Durable provider answer, committed before any model analysis."""

    __tablename__ = "server_captures"
    __table_args__ = (UniqueConstraint("run_id", "query_id", "service"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("control_runs.id"), index=True)
    query_id: Mapped[str] = mapped_column(String(32))
    service: Mapped[str] = mapped_column(String(40))
    check_id: Mapped[str] = mapped_column(String(100), unique=True)
    answer_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderAccount(Base):
    """A database mutex and shared cooldown for each server collection engine."""
    __tablename__ = "provider_accounts"
    service: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NewsPost(Base):
    __tablename__ = "news_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ProviderTask(Base):
    """Submission intent survives a crash before the upstream task handle arrives."""
    __tablename__ = "provider_tasks"
    check_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("control_runs.id"), index=True)
    query_id: Mapped[str] = mapped_column(String(32))
    service: Mapped[str] = mapped_column(String(40), index=True)
    submission_token: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(24), index=True)
    task_id: Mapped[str | None] = mapped_column(String(200))
    answer_json: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    history_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ControlLink(Base):
    __tablename__ = "control_links"
    __table_args__ = (UniqueConstraint("user_id", "device_id", "local_project_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    local_project_id: Mapped[int] = mapped_column(Integer)
    project_id: Mapped[str] = mapped_column(ForeignKey("control_projects.id"))


class DeviceGrant(Base):
    __tablename__ = "device_grants"
    token_hash: Mapped[str] = mapped_column(ForeignKey("sessions.token_hash", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))


class DeviceConnect(Base):
    __tablename__ = "device_connect"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def make_session_factory(database_url: str):
    pool = {"pool_size": 30, "max_overflow": 0} if database_url.startswith(("postgresql://", "postgresql+")) else {}
    engine = create_engine(database_url, pool_pre_ping=True, **pool)
    return engine, sessionmaker(engine, expire_on_commit=False)
