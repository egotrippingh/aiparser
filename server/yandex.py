"""Серверный OAuth Яндекс ID: code + PKCE, без токенов Яндекса в браузере."""

from __future__ import annotations

import base64
import hashlib
import re
from urllib.parse import urlencode

import httpx


class YandexError(RuntimeError):
    pass


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def profile_avatar_id(profile: dict) -> str | None:
    value = profile.get("default_avatar_id")
    if (profile.get("is_avatar_empty") is False and isinstance(value, str)
            and len(value) <= 190 and re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)?", value)):
        return value
    return None


class YandexOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str,
                 transport: httpx.BaseTransport | None = None, *, request_avatar: bool = False):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.transport = transport
        self.request_avatar = request_avatar

    def authorize_url(self, state: str, verifier: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "login:info login:email",
            "force_confirm": "yes",
            "state": state,
            "code_challenge": challenge(verifier),
            "code_challenge_method": "S256",
        }
        if self.request_avatar:
            params["optional_scope"] = "login:avatar"
        return "https://oauth.yandex.ru/authorize?" + urlencode(params)

    def profile(self, code: str, verifier: str) -> dict:
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                token_response = client.post("https://oauth.yandex.ru/token", data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code_verifier": verifier,
                })
                token_response.raise_for_status()
                access_token = token_response.json()["access_token"]
                info_response = client.get("https://login.yandex.ru/info", params={"format": "json"},
                                           headers={"Authorization": f"OAuth {access_token}"})
                info_response.raise_for_status()
                profile = info_response.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise YandexError("Не удалось завершить вход через Яндекс") from exc
        if not isinstance(profile, dict) or str(profile.get("client_id")) != self.client_id:
            raise YandexError("Яндекс вернул профиль другого приложения")
        if not profile.get("id"):
            raise YandexError("Яндекс не вернул ID пользователя")
        return profile
