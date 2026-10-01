"""Opt-in reporting: only an allowlisted error envelope leaves the process."""
from __future__ import annotations
import asyncio
import os
import re
import traceback
from pathlib import Path
from typing import Any

_UUID = re.compile(r"^[a-f0-9]{32}$")
_DSN = re.compile(r"^https://[A-Za-z0-9]+@[A-Za-z0-9.-]+/\d+$")
_enabled = False
_ROOT = Path(__file__).resolve().parent
_VALUES = {"component": {"agent", "server"}, "operation": {"startup", "saved_sessions", "local_api", "scan_query", "control_sync", "request", "ai_analyze", "ai_arbitrate", "scheduler", "payment_reconcile", "start_job", "recompute", "uncaught"}, "provider": {"chatgpt", "perplexity", "alice", "google_aio"}}
_TYPES = {"RuntimeError", "ValueError", "KeyError", "TypeError", "AttributeError", "OSError", "ConnectionError", "TimeoutError", "AIError", "AdapterError", "ServiceUnavailableError", "BillingError", "StorageError", "CoinsoError"}


def _safe_id(value: object) -> str | None:
    return value if isinstance(value, str) and _UUID.fullmatch(value) else None


def _expected(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return True
    try:
        from app.scanner.adapters.base import AuthRequiredError, CaptchaError, ProviderQuotaError
        if isinstance(exc, (AuthRequiredError, CaptchaError, ProviderQuotaError)):
            return True
    except ImportError:
        pass
    try:
        from app.billing import BillingError
        return isinstance(exc, BillingError) and exc.status_code in {401, 402, 403, 409, 422, 429}
    except ImportError:
        return False


def _filename(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    path = raw.replace("\\", "/")
    if Path(path).is_absolute():
        try:
            path = Path(path).resolve().relative_to(_ROOT).as_posix()
        except (ValueError, OSError):
            return None
    if re.fullmatch(r"(?:app|server)/[A-Za-z0-9_/-]+\.py|(?:telemetry|desktop)\.py", path) and ".." not in path:
        return path
    return None


def _transport_event(event: dict[str, Any]) -> dict[str, Any] | None:
    values = (event.get("exception") or {}).get("values", [])
    if not values or not isinstance(values[0], dict):
        return None
    value = values[0]
    frames = [{"filename": name, "lineno": frame["lineno"]}
              for frame in (value.get("stacktrace") or {}).get("frames", [])
              if isinstance(frame, dict) and (name := _filename(frame.get("filename")))
              and isinstance(frame.get("lineno"), int) and frame["lineno"] > 0]
    tags = {key: candidate for key, candidate in (event.get("tags") or {}).items()
            if key in _VALUES and isinstance(candidate, str) and candidate in _VALUES[key]}
    fresh: dict[str, Any] = {"platform": "python", "level": "error", "exception": {"values": [{"type": value.get("type") if value.get("type") in _TYPES else "Error", "stacktrace": {"frames": frames}}]}, "tags": tags}
    if event_id := _safe_id(event.get("event_id")):
        fresh["event_id"] = event_id
    release = event.get("release")
    if isinstance(release, str) and (release == "local" or re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}|[a-f0-9]{40}", release)):
        fresh["release"] = release
    if event.get("environment") in {"development", "test", "production"}:
        fresh["environment"] = event["environment"]
    if user_id := _safe_id((event.get("user") or {}).get("id")):
        fresh["user"] = {"id": user_id}
    if run_id := _safe_id(((event.get("contexts") or {}).get("run") or {}).get("id")):
        fresh["contexts"] = {"run": {"id": run_id}}
    return fresh


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    exc = hint.get("exc_info", (None, None, None))[1]
    if not isinstance(exc, BaseException) or _expected(exc):
        return None
    return _transport_event({**event, "exception": {"values": [{"type": type(exc).__name__, "stacktrace": {"frames": [{"filename": item.filename, "lineno": item.lineno} for item in traceback.extract_tb(exc.__traceback__)]}}]}})


def _transport_type():
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.transport import HttpTransport

    class SafeHttpTransport(HttpTransport):
        @staticmethod
        def clean(envelope):
            fresh = Envelope()
            event = envelope.get_event()
            if event and (safe := _transport_event(event)):
                fresh.headers = {"event_id": safe["event_id"]} if "event_id" in safe else {}
                fresh.add_event(safe)
            return fresh

        def capture_envelope(self, envelope):
            clean = self.clean(envelope)
            if clean.items:
                super().capture_envelope(clean)

        def _serialize_envelope(self, envelope):
            return super()._serialize_envelope(self.clean(envelope))

    return SafeHttpTransport


def init(*, component: str, dsn: str | None = None, release: str | None = None) -> bool:
    global _enabled
    if _enabled:
        return True
    dsn = os.environ.get("SENTRY_DSN", "") if dsn is None else dsn
    if not _DSN.fullmatch(dsn):
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.excepthook import ExcepthookIntegration
        from sentry_sdk.integrations.threading import ThreadingIntegration
        from sentry_sdk.integrations.dedupe import DedupeIntegration
        sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0, profiles_sample_rate=0,
                        enable_logs=False, include_local_variables=False, max_breadcrumbs=0,
                        default_integrations=False, integrations=[ExcepthookIntegration(), ThreadingIntegration(propagate_scope=False), DedupeIntegration()],
                        before_send=_before_send, send_client_reports=False, transport=_transport_type(),
                        release=release or os.environ.get("AIRATE_RELEASE", "local"), environment=os.environ.get("APP_ENV", "development"))
        sentry_sdk.set_tag("component", component)
        sentry_sdk.set_tag("operation", "uncaught")
        _enabled = True
    except Exception:
        return False
    return True


def watch_loop(component: str) -> None:
    if not _enabled:
        return
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()

    def handler(loop, context):
        if isinstance(context.get("exception"), BaseException):
            capture(context["exception"], component=component, operation="uncaught")
        if previous:
            previous(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def capture(exc: BaseException, *, component: str, operation: str, provider: str | None = None,
            user_id: object | None = None, run_id: object | None = None) -> None:
    if not _enabled:
        return
    try:
        if _expected(exc):
            return
        import sentry_sdk
        with sentry_sdk.new_scope() as scope:
            scope.set_user({"id": safe} if (safe := _safe_id(user_id)) else {})
            scope.set_context("run", {"id": safe} if (safe := _safe_id(run_id)) else {})
            scope.set_tag("provider", "")
            for key, candidate in {"component": component, "operation": operation, "provider": provider}.items():
                if candidate in _VALUES[key]:
                    scope.set_tag(key, candidate)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def flush() -> None:
    if _enabled:
        try:
            import sentry_sdk
            sentry_sdk.flush(timeout=1)
        except Exception:
            pass
