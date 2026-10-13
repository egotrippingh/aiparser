"""AI website collection; model inference is deliberately a separate service."""
from __future__ import annotations

import asyncio
import os
import re
import threading
from urllib.parse import urlsplit

import httpx

from shared.errors import AdapterError

SERVICES = {"chatgpt", "perplexity", "gemini"}
BASE = "https://api.scrapeless.com/api/v2/scraper"
# Connections are shared across run event loops; task concurrency is enforced in SQL.
HTTP_SLOTS = threading.BoundedSemaphore(32)


def configured():
    return bool(os.environ.get("SCRAPELESS_API_KEY", "").strip())


def limits():
    return {s: max(1, min(100, int(os.environ.get(f"SCRAPELESS_{s.upper()}_CONCURRENCY",
        "100")))) for s in SERVICES}


class SubmissionUnknown(AdapterError):
    """The supplier may have accepted the POST; do not send it again."""


class CollectionDeferred(AdapterError):
    """Leave a request unfinished instead of publishing an error as evidence."""


class IncompleteAnswer(CollectionDeferred):
    """A terminal task has no usable answer and may be collected again."""


class Rejected(AdapterError):
    def __init__(self, status):
        super().__init__(f"Сервис сбора отклонил запрос (HTTP {status})")
        self.status = status


def safe_url(value):
    if not isinstance(value, str) or len(value) > 4000:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme in ("http", "https") and parts.hostname and not parts.username and not parts.password:
            return value
    except ValueError:
        pass
    return None


def evidence(result):
    if not isinstance(result, dict) or not isinstance(result.get("result_text"), str) or not result["result_text"].strip():
        raise IncompleteAnswer("Сервис сбора вернул пустой или неполный ответ")
    text = result["result_text"]
    if len(text) > 60000:
        raise CollectionDeferred("Ответ превышает допустимый размер; требуется проверка администратора")
    sources, cards = [], []

    def add(value):
        if isinstance(value, str):
            url, title, snippet = safe_url(value), "", ""
        elif isinstance(value, dict):
            url = safe_url(value.get("url") or value.get("link"))
            title = value.get("title") or value.get("name") or ""
            snippet = value.get("snippet") or ""
        else:
            return
        if url and url not in sources and len(sources) < 50:
            sources.append(url)
            if isinstance(title, str) and isinstance(snippet, str) and (title or snippet):
                cards.append({"url": url, "title": title[:2000], "text": snippet[:4000]})

    for field in ("links", "search_result", "content_references", "web_results", "citations"):
        values = result.get(field)
        if isinstance(values, list):
            for value in values[:100]:
                add(value)
    for match in re.finditer(r"https?://[^\s<>\]\"']+", text):
        value = match.group().rstrip(".,;:!?")
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        add(value)
    return {"shown": True, "main_text": text, "answer_text": text, "cards_text": "",
        "format": "markdown", "content": [text], "products": [], "source_cards": cards, "sources": sources}


class ScrapelessClient:
    def __init__(self, *, transport=None):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=15),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=16),
            headers={"x-api-token": os.environ.get("SCRAPELESS_API_KEY", "")}, transport=transport)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def request(self, method, path, **kwargs):
        while not HTTP_SLOTS.acquire(blocking=False):
            await asyncio.sleep(.05)
        try:
            return await self.client.request(method, BASE + path, **kwargs)
        finally:
            HTTP_SLOTS.release()

    async def submit(self, service, prompt, country):
        if service not in SERVICES or not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("Неверный сервис или страна сбора")
        input_data = {"prompt": prompt, "country": country}
        if service in {"chatgpt", "perplexity"}:
            input_data["web_search"] = True
        if service in {"chatgpt", "gemini"}:
            input_data["shopping"] = False
        try:
            response = await self.request("POST", "/request", json={"actor": "scraper." + service, "input": input_data})
            if response.status_code in (400, 401, 402, 403, 429):
                raise Rejected(response.status_code)
            if response.status_code not in (200, 201, 202):
                raise SubmissionUnknown("Неизвестен исход отправки; требуется сверка задачи у сервиса сбора")
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                data = data["data"]
            task_id = data.get("task_id") if isinstance(data, dict) else None
            if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
                raise SubmissionUnknown("Сервис сбора не подтвердил идентификатор отправленной задачи")
            return task_id
        except (httpx.HTTPError, ValueError) as exc:
            raise SubmissionUnknown("Неизвестен исход отправки; повторная отправка заблокирована") from exc

    async def poll(self, task_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
            raise ValueError("Неверный идентификатор задачи")
        try:
            response = await self.request("GET", "/result/" + task_id)
            if response.status_code in (202, 429) or response.status_code >= 500:
                return "pending", None
            if response.status_code == 410:
                return "expired", None
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                data = data["data"]
            if response.status_code == 400 and isinstance(data, dict) and data.get("message") == "task expired.":
                return "expired", None
            if response.status_code != 200 or not isinstance(data, dict):
                raise CollectionDeferred("Получение ответа временно недоступно")
            status = data.get("status")
            if status in ("pending", "running"):
                return "pending", None
            if status == "failed":
                return "failed", None
            if status == "success":
                try:
                    return "success", evidence(data.get("task_result"))
                except IncompleteAnswer:
                    return "failed", None
            raise CollectionDeferred("Сервис сбора вернул неизвестный статус задачи")
        except (httpx.HTTPError, ValueError):
            return "pending", None
