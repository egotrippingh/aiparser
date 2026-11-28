"""Disposable browser E2E check for the competitor and citation reports.

It starts the real FastAPI application against a new SQLite file and exercises the
built ``web/`` bundle through a real Playwright browser.  It is intentionally not
part of pytest: run it after rebuilding the frontend, for example::

    .\\.venv\\Scripts\\python.exe scripts/e2e_project_analysis.py
    .\\.venv\\Scripts\\python.exe scripts/e2e_project_analysis.py --serve

``--serve`` leaves the loopback preview running and prints the disposable login.
It never reads a .env file or uses provider, production, or user data.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Do this before importing server code: a local fixture must not inherit a shell's
# database URL, mailer, storage, payment, or paid-provider credentials.
for _key in (
    "DATABASE_URL", "COINSO_SECRET_KEY", "COINSO_PROJECT_ID", "OPENROUTER_API_KEY",
    "OPENROUTER_MANAGEMENT_KEY", "SCRAPELESS_API_KEY", "AIPARSER_XMLRIVER_USER",
    "AIPARSER_XMLRIVER_KEY", "S3_SCREENSHOTS_BUCKET", "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY", "YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET", "SMTP_HOST",
    "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "PUBLIC_BASE_URL", "ADMIN_BASE_URL",
    "AIRATE_ADMIN_PREVIEW", "SENTRY_DSN",
):
    os.environ.pop(_key, None)
os.environ["APP_ENV"] = "test"

import uvicorn
from fastapi.testclient import TestClient
from playwright.async_api import Browser, Page, Playwright, Route, async_playwright, expect
from sqlalchemy import select

from server.app import create_app
from server.models import CloudResult, ControlProject, ProjectMember, User, Wallet, make_session_factory
from server.test_accounts import register_account

HOST = "127.0.0.1"
OWNER_EMAIL = "owner@competitors.preview.test"
VIEWER_EMAIL = "viewer@competitors.preview.test"
PASSWORD = "competitor-preview-pass-123"


@dataclass(frozen=True)
class Fixture:
    app: object
    project_id: str


def _auth(client: TestClient, email: str) -> dict[str, str]:
    response = register_account(client, json={"email": email, "password": PASSWORD})
    if response.status_code != 201:
        raise RuntimeError(f"Could not create disposable account: {response.text}")
    return {"Authorization": "Bearer " + response.json()["token"]}


def make_fixture(work: Path, *, preconfigure_competitor: bool = False) -> Fixture:
    """Create accounts/project through API, then add controlled scan history via ORM."""
    database_url = f"sqlite:///{work / 'preview.db'}"
    app = create_app(database_url=database_url)
    with closing(TestClient(app)) as client:
        owner = _auth(client, OWNER_EMAIL)
        _auth(client, VIEWER_EMAIL)
        created = client.post("/api/v1/control/projects", headers=owner, json={
            "name": "Бренд QA", "brand_name": "Бренд QA",
            "queries": [
                {"text": "Где купить Бренд QA", "group_tag": "Покупка"},
                {"text": "Сравнение Бренд QA и Риваль", "group_tag": "Сравнение"},
                {"text": "Поддержка Бренд QA", "group_tag": "Поддержка"},
            ],
            "config": {"services": ["google_aio", "chatgpt", "perplexity"],
                       "brand_domains": ["brand.example.test"]},
        })
        if created.status_code != 201:
            raise RuntimeError(f"Could not create disposable project: {created.text}")
        project = created.json()
        if preconfigure_competitor:
            saved = client.put(
                f"/api/v1/control/projects/{project['id']}/mentions/competitor-settings", headers=owner,
                json={"revision": 0, "competitors": [
                    {"name": "Риваль QA", "aliases": ["Риваль", "Rival QA"],
                     "domains": ["rival.example.test", "shop.rival.example.test"]},
                    {"name": "Вектор", "aliases": [], "domains": ["vector.example.test"]},
                ]},
            )
            if saved.status_code != 200:
                raise RuntimeError(f"Could not seed the competitor editor: {saved.text}")
    engine, sessions = make_session_factory(database_url)
    today = date.today()
    with sessions() as db:
        row_project = db.get(ControlProject, project["id"])
        if row_project is None:
            raise RuntimeError("Disposable project was not persisted")
        viewer_id = db.scalar(select(User.id).where(User.email == VIEWER_EMAIL))
        if viewer_id is None:
            raise RuntimeError("Disposable viewer was not persisted")
        db.add(ProjectMember(project_id=row_project.id, user_id=viewer_id, role="viewer"))
        wallet = db.get(Wallet, row_project.user_id)
        if wallet is not None:
            wallet.balance_kopeks = 10_000
        rows = [
            # Own + competitor + external citation, including the duplicate fragment.
            (0, "google_aio", 2, "found", "Бренд QA и Риваль QA доступны. См. [Каталог QA](https://external.example.test/review).",
             ["https://brand.example.test/buy", "https://rival.example.test/guide#price",
              "https://rival.example.test/guide#price", "https://external.example.test/review"]),
            # Competitor wins this answer; the UI toggle must leave this row visible.
            (1, "chatgpt", 1, "not_found", "Лучше выбрать Риваль QA. См. [Каталог QA](https://external.example.test/compare).",
             ["https://shop.rival.example.test/compare", "https://external.example.test/compare",
              "https://external.example.test/review"]),
            # Brand present without a competitor citation.
            (2, "perplexity", 1, "found", "Бренд QA отвечает на вопросы поддержки. Также вопросы принимает Вектор.",
             ["https://brand.example.test/help", "https://external.example.test/help"]),
            # An absent AI block and an error must remain visible as distinct states.
            (0, "chatgpt", 0, "skipped", "", []),
            (1, "google_aio", 0, "error", "", []),
        ]
        for index, (query_index, service, days_ago, status, answer, sources) in enumerate(rows, 1):
            query = project["queries"][query_index]
            row = CloudResult(
                user_id=row_project.user_id, device_id="e" * 32,
                local_result_id=index, local_project_id=1, project_id=row_project.id,
                project_name=row_project.name, brand_name=row_project.brand_name,
                query_id=query["id"], query_text=query["text"], group_tag=query.get("group_tag", ""),
                service=service, scan_date=(today - timedelta(days=days_ago)).isoformat(), status=status,
                answer_text=answer, evidence_quote="Фрагмент доказательства QA" if answer else "",
                mention_types_json=json.dumps(["text"] if status == "found" else []),
                sources_json=json.dumps(sources),
                error_message="Контролируемая ошибка QA" if status == "error" else "",
            )
            db.add(row)
        db.commit()
    engine.dispose()
    return Fixture(app=app, project_id=project["id"])


class LocalServer:
    def __init__(self, app: object, port: int) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.bind((HOST, port))
        except OSError:
            self.socket.close()
            raise
        self.url = f"http://{HOST}:{self.socket.getsockname()[1]}"
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]},
                                       name="competitor-e2e-server", daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError(f"Preview server did not start at {self.url}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out starting preview server at {self.url}")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.socket.close()


async def _launch(playwright: Playwright, browser_name: str) -> Browser:
    if browser_name == "edge":
        return await playwright.chromium.launch(channel="msedge", headless=True)
    return await getattr(playwright, browser_name).launch(headless=True)


async def _login(page: Page, base_url: str, email: str) -> None:
    await page.goto(f"{base_url}/cabinet/", wait_until="domcontentloaded")
    await page.get_by_label("Электронная почта").fill(email)
    await page.get_by_label("Пароль", exact=True).fill(PASSWORD)
    await page.get_by_role("button", name="Войти").click()
    await page.get_by_role("link", name="Конкуренты", exact=True).wait_for()


async def _assert_no_horizontal_overflow(page: Page, width: int) -> None:
    await page.set_viewport_size({"width": width, "height": 900})
    overflow = await page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) > window.innerWidth")
    if overflow:
        raise AssertionError(f"Body overflows horizontally at {width}px")
    main = page.locator(".project-analysis-page .app-main")
    assert await main.evaluate("(element) => getComputedStyle(element).paddingInlineStart") == ("16px" if width <= 700 else "24px")
    title = page.locator(".heading-title h1")
    assert "Onest" in await title.evaluate("(element) => getComputedStyle(element).fontFamily")
    font_loaded = await page.evaluate("""async () =>
        (await document.fonts.load('610 16px "Onest Cabinet"', "Конкуренты")).some(font => font.status === "loaded")""")
    assert font_loaded
    control = page.locator(".report-calendar-trigger")
    assert await control.evaluate("(element) => element.getBoundingClientRect().height") == (36 if width <= 700 else 32)
    assert await page.locator(".sidebar .nav-link svg").first.evaluate("(element) => element.getBoundingClientRect().width") == 16


async def _open_evidence(page: Page, query: str, body: str) -> None:
    await page.get_by_role("button", name=re.compile(re.escape(query))).click()
    answer = page.get_by_role("dialog", name=query, exact=True)
    await expect(answer).to_contain_text(body)
    await answer.get_by_role("button", name="Закрыть ответ").click()
    await expect(answer).to_have_count(0)


async def _owner_flow(browser: Browser, base_url: str, project_id: str, artifacts: Path | None) -> None:
    context = await browser.new_context(viewport={"width": 1440, "height": 1000})
    page = await context.new_page()
    try:
        await _login(page, base_url, OWNER_EMAIL)
        await page.get_by_role("link", name="Конкуренты", exact=True).click()
        await page.get_by_role("button", name="Настроить конкурентов").click()
        dialog = page.get_by_role("dialog", name="Настроить конкурентов")
        await dialog.get_by_label("Название").fill("Риваль QA")
        await dialog.get_by_label("Варианты написания").fill("Риваль\nRival QA")
        await dialog.get_by_label("Домены").fill("rival.example.test\nshop.rival.example.test")
        await dialog.get_by_role("button", name="Добавить конкурента").click()
        second = dialog.get_by_role("group", name="Конкурент 2")
        await second.get_by_label("Название").fill("Вектор")
        await second.get_by_label("Домены").fill("vector.example.test")
        await dialog.get_by_role("button", name="Сохранить").click()
        row = page.get_by_role("row", name=re.compile("^Риваль QA"))
        await expect(row).to_be_visible()
        await page.reload(wait_until="domcontentloaded")
        await expect(row).to_be_visible()
        await expect(row.locator("td strong")).to_have_text("2")
        await expect(row.locator("td small")).to_have_text(re.compile("50\\s*%"))
        await expect(row.get_by_role("cell").nth(1)).to_have_text("1")
        vector = page.get_by_role("row", name=re.compile("^Вектор"))
        await expect(vector.get_by_role("cell").nth(1)).to_have_text("0")
        settings = await context.request.get(f"{base_url}/api/v1/control/projects/{project_id}/mentions/competitor-settings")
        assert settings.ok
        assert (await settings.json())["competitors"] == [{
            "name": "Риваль QA", "aliases": ["Риваль", "Rival QA"],
            "domains": ["rival.example.test", "shop.rival.example.test"],
        }, {"name": "Вектор", "aliases": [], "domains": ["vector.example.test"]}]
        if artifacts is not None:
            await page.screenshot(path=artifacts / "competitors-1440.png")

        failed_filter = False

        async def fail_first_filter(route: Route) -> None:
            nonlocal failed_filter
            query = parse_qs(urlsplit(route.request.url).query)
            if not failed_filter and query.get("search") == ["Где купить Бренд QA"]:
                failed_filter = True
                await route.fulfill(status=503, json={"detail": "Контролируемая ошибка QA"})
                return
            await route.continue_()

        await context.route("**/mentions/competitors**", fail_first_filter)
        query_filter = page.get_by_label("Поиск по запросам")
        await query_filter.fill("Где купить Бренд QA")
        alert = page.get_by_role("alert").filter(has_text="Контролируемая ошибка QA")
        await expect(alert).to_be_visible()
        await query_filter.fill("Поддержка Бренд QA")
        await expect(row.locator("td strong")).to_have_text("0")
        await query_filter.fill("Где купить Бренд QA")
        await expect(row.locator("td strong")).to_have_text("1")
        await expect(alert).to_have_count(0)
        await context.unroute("**/mentions/competitors**", fail_first_filter)
        await query_filter.clear()
        gaps = page.get_by_role("switch", name="Только где нас обходят")
        await gaps.press("Space")
        await expect(gaps).to_be_checked()
        await expect(vector).to_have_count(0)
        await page.get_by_role("button", name="Ответы · Риваль QA").click()
        await expect(page.get_by_role("button", name=re.compile("Где купить Бренд QA"))).to_have_count(0)
        await _open_evidence(page, "Сравнение Бренд QA и Риваль", "Лучше выбрать Риваль QA.")
        if artifacts is not None:
            await _assert_no_horizontal_overflow(page, 390)
            await page.screenshot(path=artifacts / "competitors-390.png")
        for width in (320, 390, 1440):
            await _assert_no_horizontal_overflow(page, width)

        await page.get_by_role("link", name="Источники", exact=True).click()
        pages = page.get_by_role("link", name="Страницы", exact=True)
        domains = page.get_by_role("link", name="Домены с упоминанием бренда", exact=True)
        guide = "https://rival.example.test/guide"
        comparison = "https://shop.rival.example.test/compare"
        await expect(page.get_by_role("link", name=guide, exact=True)).to_be_visible()
        if artifacts is not None:
            await page.screenshot(path=artifacts / "cited-pages-1440.png")
        await domains.click()
        await expect(page.get_by_role("link", name=re.compile(r"^rival\.example\.test"))).to_be_visible()
        await pages.click()
        await page.get_by_role("button", name="Тип источника").click()
        await page.get_by_role("option", name="Сайты конкурентов").click()
        await expect(page.get_by_role("link", name=comparison, exact=True)).to_be_visible()
        await expect(page.get_by_role("link", name="https://brand.example.test/buy", exact=True)).to_have_count(0)

        page_filter = page.get_by_label("Поиск по URL")
        await page_filter.fill("rival.example.test/guide")
        citation = page.get_by_role("row").filter(has=page.get_by_role("link", name=guide, exact=True))
        await expect(citation.get_by_role("cell").nth(0)).to_have_text("1")
        await page.get_by_role("button", name=f"Ответы · {guide}").click()
        await _open_evidence(page, "Где купить Бренд QA", "Бренд QA и Риваль QA доступны.")
        if artifacts is not None:
            await _assert_no_horizontal_overflow(page, 390)
            await page.screenshot(path=artifacts / "cited-pages-390.png")
        for width in (320, 390, 1440):
            await _assert_no_horizontal_overflow(page, width)

        await page_filter.clear()
        await page.get_by_role("button", name="Группа запросов").click()
        await page.get_by_role("option", name="Сравнение").click()
        await expect(page.get_by_role("link", name=comparison, exact=True)).to_be_visible()
        await expect(page.get_by_role("link", name=guide, exact=True)).to_have_count(0)
        await page.get_by_role("button", name="Группа запросов").click()
        await page.get_by_role("option", name="Все группы").click()
        await expect(page.get_by_role("link", name=guide, exact=True)).to_be_visible()
        await page.locator(".report-calendar-trigger").click()
        dates = page.get_by_role("dialog", name="Даты отчёта")
        day = (date.today() - timedelta(days=2)).isoformat()
        await dates.get_by_label("Первая дата").fill(day)
        await dates.get_by_label("Последняя дата").fill(day)
        await dates.get_by_role("button", name="Применить").click()
        await expect(page.get_by_role("link", name=guide, exact=True)).to_be_visible()
        await expect(page.get_by_role("link", name=comparison, exact=True)).to_have_count(0)
    finally:
        await context.close()


async def _viewer_flow(browser: Browser, base_url: str, project_id: str) -> None:
    context = await browser.new_context(viewport={"width": 390, "height": 900})
    page = await context.new_page()
    try:
        await _login(page, base_url, VIEWER_EMAIL)
        await page.get_by_role("link", name="Конкуренты", exact=True).click()
        await expect(page.get_by_role("row", name=re.compile("^Риваль QA"))).to_be_visible()
        await expect(page.get_by_role("button", name="Настроить конкурентов")).to_have_count(0)
        response = await context.request.put(
            f"{base_url}/api/v1/control/projects/{project_id}/mentions/competitor-settings",
            data={"revision": 1, "competitors": []}, headers={"X-AI-Client": "browser"},
        )
        assert response.status in (403, 404)
        await page.get_by_role("link", name="Источники", exact=True).click()
        await expect(page.get_by_role("link", name="https://rival.example.test/guide", exact=True)).to_be_visible()
    finally:
        await context.close()


async def run(browser_name: str, base_url: str, project_id: str, artifacts: Path | None) -> None:
    async with async_playwright() as playwright:
        browser = await _launch(playwright, browser_name)
        try:
            await _owner_flow(browser, base_url, project_id, artifacts)
            await _viewer_flow(browser, base_url, project_id)
        finally:
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="Keep the disposable preview server running for a human")
    parser.add_argument("--browser", choices=("edge", "firefox", "webkit"), default="edge",
                        help="Browser engine for the automated flow (default: installed Edge channel)")
    parser.add_argument("--port", type=int, default=0, help="Loopback port; defaults to a free port")
    parser.add_argument("--artifacts", type=Path, help="Optional directory for preview screenshots")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.artifacts is not None:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="airate-competitor-citations-", ignore_cleanup_errors=True) as temp:
        fixture = make_fixture(Path(temp), preconfigure_competitor=args.serve)
        server = LocalServer(fixture.app, args.port)
        try:
            server.start()
            if args.serve:
                print(json.dumps({"url": f"{server.url}/cabinet/#/project/{fixture.project_id}/competitors",
                                  "owner": OWNER_EMAIL, "viewer": VIEWER_EMAIL, "password": PASSWORD}), flush=True)
                server.thread.join()
            else:
                asyncio.run(run(args.browser, server.url, fixture.project_id, args.artifacts))
        except KeyboardInterrupt:
            return 130
        finally:
            server.stop()
            fixture.app.state.payment_sessions.kw["bind"].dispose()
    if args.serve:
        return 0
    print("Competitor/citation browser E2E passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
