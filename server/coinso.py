"""Coinso standard checkout. All invoice amounts are RUB, including crypto."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from threading import Lock
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx


class CoinsoError(RuntimeError):
    pass


def kopeks(value: str | int | float) -> int:
    try:
        rub = Decimal(str(value))
    except InvalidOperation as exc:
        raise CoinsoError("Некорректная сумма платежа") from exc
    if not rub.is_finite() or rub < 0 or rub.as_tuple().exponent < -2:
        raise CoinsoError("Некорректная сумма платежа")
    return int(rub * 100)


def verify_webhook(raw_body: bytes, signature: str, secret_key: str) -> bool:
    if not re.fullmatch(r"[a-fA-F0-9]{64}", signature):
        return False
    expected = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


class CoinsoClient:
    def __init__(self, base_url: str, project_id: int, secret_key: str,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.secret_key = secret_key
        self.transport = transport
        self._methods_cache: tuple[float, dict] | None = None
        self._methods_lock = Lock()

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                response = client.request(method, self.base_url + path, **kwargs)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CoinsoError("Не удалось связаться с платёжным сервисом. Повторите позже.") from exc
        if not isinstance(data, dict) or data.get("success") is not True:
            raise CoinsoError("Платёжный сервис не подтвердил запрос")
        return data

    def payment_methods(self) -> dict:
        # Fetch enabled methods/limits, not a hard-coded list of coins or networks.
        with self._methods_lock:
            if self._methods_cache and time.monotonic() < self._methods_cache[0]:
                return self._methods_cache[1]
            data = self._request("GET", "/payment/methods", params={"project_id": self.project_id},
                                 headers={"Authorization": f"Bearer {self.secret_key}"})
            if data.get("currency") != "RUB" or not isinstance(data.get("methods"), list):
                raise CoinsoError("Не удалось получить способы оплаты")
            self._methods_cache = time.monotonic() + 30, data
            return data

    def create_invoice(self, *, order_id: str, amount_kopeks: int, method: str, email: str,
                       return_url: str) -> dict:
        payload = {
            "project_id": self.project_id,
            "amount": float(Decimal(amount_kopeks) / 100),
            "description": f"Пополнение баланса AIRate, заказ {order_id}",
            "custom": order_id,
            "method": method,
            "integration_type": "standard",
            "client_email": email,
            "success_url": payment_return_url(return_url, "success"),
            "fail_url": payment_return_url(return_url, "failed"),
        }
        data = self._request("POST", "/payment/create", json=payload,
                             headers={"Authorization": f"Bearer {self.secret_key}"})
        try:
            link = urlsplit(data.get("payment_url", ""))
            valid = (isinstance(data.get("invoice_id"), str)
                     and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", data["invoice_id"])
                     and link.scheme == "https" and link.hostname == "coinso.io"
                     and not link.username and not link.password and link.port in (None, 443))
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise CoinsoError("Платёжный сервис вернул некорректный счёт")
        return data

    def invoice_status(self, invoice_id: str) -> dict:
        return self._request("GET", "/payment/status", params={"uuid": invoice_id})


def payment_return_url(url: str, outcome: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query)); query["payment"] = outcome
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def payment_options(client: CoinsoClient, minimum: int, amount: int | None = None) -> list[dict]:
    methods = []
    for row in client.payment_methods()["methods"]:
        if not isinstance(row, dict) or row.get("method") not in {"sbp", "crypto"}:
            continue
        floor = max(minimum, kopeks(row.get("min_amount", 0)))
        ceiling = min(10_000_000, kopeks(row["max_amount"])) if row.get("max_amount") is not None else 10_000_000
        available = row.get("available", True) is True and floor <= ceiling
        if amount is not None:
            available = available and floor <= amount <= ceiling
        methods.append({"method": row["method"], "min_kopeks": floor, "max_kopeks": ceiling,
                        "available": available})
    return methods


def valid_payment_currency(method: str, currency: object) -> bool:
    if method in {"sbp", "card", "p2p_sbp", "p2p_card"}:
        return currency == "RUB"
    # /payment/status.amount is RUB; currency is the last attempt's coin code.
    return method == "crypto" and isinstance(currency, str) and bool(re.fullmatch(r"[a-z0-9_]{1,40}", currency))
