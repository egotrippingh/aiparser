"""Изолированный клиент Coinso: СБП и карты, сверка статуса по API."""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal, InvalidOperation

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
    expected = hmac.new(secret_key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


class CoinsoClient:
    def __init__(self, base_url: str, project_id: int, secret_key: str):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.secret_key = secret_key

    def create_invoice(self, *, order_id: str, amount_kopeks: int, method: str, email: str,
                       return_url: str) -> dict:
        payload = {
            "project_id": self.project_id,
            "amount": float(Decimal(amount_kopeks) / 100),
            "description": f"Пополнение баланса AI Mentions, заказ {order_id}",
            "custom": order_id,
            "method": method,
            "integration_type": "standard",
            "client_email": email,
            "success_url": return_url,
            "fail_url": return_url,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/payment/create", json=payload,
                headers={"Authorization": f"Bearer {self.secret_key}"}, timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CoinsoError("Coinso не создал платёж") from exc
        if not data.get("success") or not data.get("invoice_id") or not data.get("payment_url"):
            raise CoinsoError(data.get("message") or "Coinso вернул неполный платёж")
        return data

    def invoice_status(self, invoice_id: str) -> dict:
        try:
            response = httpx.get(
                f"{self.base_url}/payment/status", params={"uuid": invoice_id}, timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CoinsoError("Не удалось сверить платёж с Coinso") from exc
        if not data.get("success"):
            raise CoinsoError(data.get("message") or "Coinso не подтвердил платёж")
        return data
