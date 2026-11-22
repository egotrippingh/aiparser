"""IP allowlist for the admin host (stealth 404 when denied)."""
from __future__ import annotations

import ipaddress
import os
import re
from ipaddress import IPv4Network, IPv6Network

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.models import AdminAllowedIp

Network = IPv4Network | IPv6Network
NOT_FOUND = "Страница не найдена"
_SPLIT = re.compile(r"[\s,]+")


def client_ip(request: Request) -> str:
    # Uvicorn uses forwarded headers only for explicitly trusted proxies.
    return request.client.host if request.client else ""


def parse_cidr(value: str) -> str:
    text = (value or "").strip()
    if not text or len(text) > 64:
        raise ValueError("Укажите IPv4/IPv6 или CIDR")
    try:
        return str(ipaddress.ip_network(text, strict=False))
    except ValueError as exc:
        raise ValueError("Укажите корректный IPv4/IPv6 или CIDR") from exc


def env_cidrs() -> list[str]:
    raw = os.environ.get("ADMIN_ALLOWED_IPS", "")
    result: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT.split(raw.strip()) if raw.strip() else []:
        try:
            cidr = parse_cidr(part)
        except ValueError:
            continue
        if cidr not in seen:
            seen.add(cidr)
            result.append(cidr)
    return result


def _networks(cidrs: list[str]) -> list[Network]:
    networks: list[Network] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return networks


def db_cidrs(db: Session) -> list[str]:
    return list(db.scalars(select(AdminAllowedIp.cidr).order_by(AdminAllowedIp.id)))


def entry_allowed(request: Request, db: Session) -> bool:
    host = client_ip(request)
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    for network in _networks(env_cidrs() + db_cidrs(db)):
        if address in network:
            return True
    return False


def require_admin_entry_ip(request: Request, db: Session) -> None:
    if not entry_allowed(request, db):
        raise HTTPException(404, NOT_FOUND)
