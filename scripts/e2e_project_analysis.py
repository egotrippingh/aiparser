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
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Do this before importing server code: a local fixture must not inherit a shell's
# database URL, mailer, storage, payment, or paid-provider credentials.
for _key in (
    "DATABASE_URL", "COINSO_SECRET_KEY", "COINSO_PROJECT_ID", "OPENROUTER_API_KEY",
    "OPENROUTER_MANAGEMENT_KEY", "SCRAPELESS_API_KEY", "AIPARSER_XMLRIVER_USER",
    "AIPARSER_XMLRIVER_KEY", "S3_SCREENSHOTS_BUCKET", "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY", "YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET", "SMTP_HOST",
    "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
):
    os.environ.pop(_key, None)
os.environ["APP_ENV"] = "test"

import uvicorn
from fastapi.testclient import TestClient
from playwright.async_api import Browser, Page, Playwright, async_playwright
from sqlalchemy import select

from server.app import create_app
from server.models import CloudResult, ControlProject, ProjectMember, User, Wallet, make_session_factory
from server.test_accounts import register_account

HOST = "127.0.0.1"
PORT = 8794
BASE_URL = f"http://{HOST}:{PORT}"
OWNER_EMAIL = "owner@competitors.preview.test"
VIEWER_EMAIL = "viewer@competitors.preview.test"
PASSWORD = "competitor-preview-pass-123"


@dataclass(frozen=True)
class Fixture:
    app: object
    project_id: str
    result_id: int
    db_dir: Path


def _auth(client: TestClient, email: str) -> dict[str, str]:
    response = register_account(client, json={"email": email, "password": PASSWORD})
    if response.status_code != 201:
        raise RuntimeError(f"Could not create disposable account: {response.text}")
    return {"Authorization": "Bearer " + response.json()["token"]}


def make_fixture(*, preconfigure_competitor: bool = False) -> Fixture:
    """Create accounts/project through API, then add controlled scan history via ORM."""
    work = Path(tempfile.mkdtemp(prefix="airate-competitor-citations-e2e-"))
    database_url = f"sqlite:///{work / 'preview.db'}"
    app = create_app(database_url=database_url)
    client = TestClient(app)
    owner, viewer = _auth(client, OWNER_EMAIL), _auth(client, VIEWER_EMAIL)
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
    _, sessions = make_session_factory(database_url)
    today = date.today()
    result_id = 0
    with sessions() as db:
        row_project = db.get(ControlProject, project["id"])
        if row_project is None:
            raise RuntimeError("Disposable project was not persisted")
        # The feature stores competitors with the project.  Writing the fixture
        # through the application's database keeps it independent of an editor UI.
        config = json.loads(row_project.config_json)
        # Automated mode starts empty so it verifies the editor's first blank row.
        # A human ``--serve`` preview instead opens with useful competitor filters.
        if preconfigure_competitor:
            config["competitors"] = [{
                "name": "Риваль QA", "aliases": ["Риваль", "Rival QA"],
                "domains": ["rival.example.test", "shop.rival.example.test"],
            }]
        else:
            config.pop("competitors", None)
        row_project.config_json = json.dumps(config, ensure_ascii=False)
        viewer_id = db.scalar(select(User.id).where(User.email == VIEWER_EMAIL))
        if viewer_id is None:
            raise RuntimeError("Disposable viewer was not persisted")
        db.add(ProjectMember(project_id=row_project.id, user_id=viewer_id, role="viewer"))
        wallet = db.get(Wallet, row_project.user_id)
        if wallet is not None:
            wallet.balance_kopeks = 10_000
        rows = [
            # Own + competitor + external citation, including the duplicate fragment.
            (0, "google_aio", 2, "found", "Бренд QA и Риваль QA доступны.",
             ["https://brand.example.test/buy", "https://rival.example.test/guide#price",
              "https://rival.example.test/guide#price", "https://external.example.test/review"]),
            # Competitor wins this answer; the UI toggle must leave this row visible.
            (1, "chatgpt", 1, "not_found", "Лучше выбрать Риваль QA.",
             ["https://shop.rival.example.test/compare", "https://external.example.test/compare"]),
            # Brand present without a competitor citation.
            (2, "perplexity", 1, "found", "Бренд QA отвечает на вопросы поддержки.",
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
            db.flush()
            if index == 1:
                result_id = row.id
        db.commit()
    return Fixture(app=app, project_id=project["id"], result_id=result_id, db_dir=work)


class LocalServer:
    def __init__(self, app: object) -> None:
        self.server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, name="competitor-e2e-server", daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError(f"Preview server did not start at {BASE_URL}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out starting preview server at {BASE_URL}")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


async def _launch(playwright: Playwright, browser_name: str) -> Browser:
    if browser_name == "edge":
        return await playwright.chromium.launch(channel="msedge", headless=True)
    return await getattr(playwright, browser_name).launch(headless=True)


async def _login(page: Page, email: str) -> None:
    await page.goto(f"{BASE_URL}/cabinet/", wait_until="domcontentloaded")
    await page.get_by_label("Email").fill(email)
    await page.get_by_label("Пароль").fill(PASSWORD)
    await page.get_by_role("button", name="Войти").click()
    await page.get_by_text("Бренд QA", exact=True).wait_for()


async def _assert_no_horizontal_overflow(page: Page, width: int) -> None:
    await page.set_viewport_size({"width": width, "height": 900})
    overflow = await page.evaluate("document.body.scrollWidth > window.innerWidth")
    if overflow:
        raise AssertionError(f"Body overflows horizontally at {width}px")


async def _owner_flow(browser: Browser, project_id: str) -> None:
    context = await browser.new_context(viewport={"width": 1440, "height": 1000})
    page = await context.new_page()
    try:
        await _login(page, OWNER_EMAIL)
        await page.get_by_role("link", name="Конкуренты").click()
        await page.get_by_role("button", name="Настроить конкурентов").click()
        dialog = page.get_by_role("dialog")
        await dialog.get_by_label("Название").fill("Риваль QA")
        await dialog.get_by_label("Варианты написания").fill("Риваль\nRival QA")
        await dialog.get_by_label("Домены").fill("rival.example.test\nshop.rival.example.test")
        await dialog.get_by_role("button", name="Сохранить").click()
        await page.get_by_text("Риваль QA", exact=True).wait_for()
        await page.reload(wait_until="domcontentloaded")
        await page.get_by_text("Риваль QA", exact=True).wait_for()
        settings = await page.evaluate("""async (id) => {
          const token = sessionStorage.getItem('aimt.account.token');
          const response = await fetch(`/api/v1/control/projects/${id}/mentions/competitor-settings`, {
            headers: token ? {Authorization: `Bearer ${token}`} : {}, credentials: 'same-origin'
          });
          return {status: response.status, body: await response.json()};
        }""", project_id)
        if settings["status"] != 200 or settings["body"].get("competitors") != [{
            "name": "Риваль QA", "aliases": ["Риваль", "Rival QA"],
            "domains": ["rival.example.test", "shop.rival.example.test"],
        }]:
            raise AssertionError(f"Competitor settings were not retained: {settings}")
        failed_filter = {"value": False}

        async def fail_first_filter(request_route) -> None:
            request_url = request_route.request.url
            query = unquote(urlsplit(request_url).query)
            if not failed_filter["value"] and "search=Где купить Бренд QA" in query:
                failed_filter["value"] = True
                await request_route.fulfill(status=503, content_type="application/json",
                                            body='{"detail":"Контролируемая ошибка QA"}')
                return
            await request_route.continue_()

        # The stale-error regression: a failure for filter A cannot remain after
        # B succeeds, including when the user returns to A.
        await context.route("**/mentions/competitors**", fail_first_filter)
        query_filter = page.get_by_label("Поиск по запросам")
        await query_filter.fill("Где купить Бренд QA")
        await page.get_by_role("alert").wait_for()
        await query_filter.fill("Поддержка Бренд QA")
        await page.get_by_text("Поддержка Бренд QA", exact=True).wait_for()
        await query_filter.fill("Где купить Бренд QA")
        await page.get_by_text("Где купить Бренд QA", exact=True).wait_for()
        if await page.get_by_role("alert").count():
            raise AssertionError("A recovered competitor report still displays the stale filter error")
        await context.unroute("**/mentions/competitors**", fail_first_filter)
        await page.get_by_role("switch", name="Только где нас обходят").click()
        await page.get_by_text("Сравнение Бренд QA и Риваль", exact=True).wait_for()
        await page.get_by_role("button", name="Ответы · Риваль QA").click()
        answer = page.get_by_role("dialog", name="Ответ ИИ")
        await answer.get_by_text("Лучше выбрать Риваль QA.", exact=True).wait_for()
        await answer.get_by_role("button", name="Закрыть").click()

        await page.get_by_role("link", name="Источники").click()
        await page.get_by_role("tab", name="Страницы").wait_for()
        await page.get_by_role("tab", name="Домены с упоминанием бренда").click()
        await page.get_by_role("button", name="Тип источника").click()
        await page.get_by_role("option", name="Сайты конкурентов").click()
        await page.get_by_label("Поиск по URL").fill("rival.example.test")
        source_row = page.get_by_text("https://rival.example.test/guide", exact=True)
        await source_row.wait_for()
        evidence_button = page.get_by_role("button", name=re.compile(
            r"Где купить Бренд QA.*Google AI Overview"))
        if await evidence_button.count() != 1:
            raise AssertionError("Expected exactly one evidence control for the filtered competitor citation")
        await evidence_button.click()
        evidence = page.get_by_role("dialog", name="Ответ ИИ")
        await evidence.get_by_text("Фрагмент доказательства QA", exact=True).wait_for()
        await evidence.get_by_role("button", name="Закрыть").click()
        await page.goto(f"{BASE_URL}/cabinet/#/project/{project_id}/source-domains", wait_until="domcontentloaded")
        await page.get_by_text("rival.example.test", exact=True).wait_for()

        # These controls must exist and be usable together with the fixture's groups/dates.
        await page.get_by_role("button", name="Даты отчёта").click()
        dates = page.get_by_role("dialog", name="Даты отчёта")
        await dates.get_by_label("Первая дата").fill((date.today() - timedelta(days=2)).isoformat())
        await dates.get_by_label("Последняя дата").fill(date.today().isoformat())
        await dates.get_by_role("button", name="Применить").click()
        await page.get_by_role("button", name="Группа запросов").click()
        await page.get_by_role("option", name="Сравнение").click()
        for width in (320, 390, 1440):
            await _assert_no_horizontal_overflow(page, width)
    finally:
        await context.close()


async def _viewer_flow(browser: Browser) -> None:
    context = await browser.new_context(viewport={"width": 390, "height": 900})
    page = await context.new_page()
    try:
        await _login(page, VIEWER_EMAIL)
        for target in ("Конкуренты", "Источники"):
            await page.get_by_role("link", name=target).click()
            await page.get_by_role("main").wait_for()
        if await page.get_by_role("button", name="Настроить конкурентов").count():
            raise AssertionError("Viewer can see the competitor editor")
    finally:
        await context.close()


async def run(browser_name: str, project_id: str) -> None:
    async with async_playwright() as playwright:
        browser = await _launch(playwright, browser_name)
        try:
            await _owner_flow(browser, project_id)
            await _viewer_flow(browser)
        finally:
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="Keep the disposable preview server running for a human")
    parser.add_argument("--browser", choices=("edge", "firefox", "webkit"), default="edge",
                        help="Browser engine for the automated flow (default: installed Edge channel)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture = make_fixture(preconfigure_competitor=args.serve)
    server = LocalServer(fixture.app)
    server.start()
    details = {"url": f"{BASE_URL}/cabinet/", "owner": OWNER_EMAIL, "viewer": VIEWER_EMAIL,
               "password": PASSWORD, "project_id": fixture.project_id, "database": str(fixture.db_dir)}
    print(json.dumps(details, ensure_ascii=False), flush=True)
    if args.serve:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
        finally:
            server.stop()
    try:
        asyncio.run(run(args.browser, fixture.project_id))
    finally:
        server.stop()
    print("Competitor/citation browser E2E passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
