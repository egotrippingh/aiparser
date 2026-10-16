"""Public crawl endpoints and indexing policy, using the shipped website assets."""

import json
import re
import struct
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from server.app import create_app


class Head(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.metas = {}
        self.canonicals = []
        self.feed(html.split("</head>")[0])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.metas[attrs.get("name", attrs.get("property"))] = attrs.get("content")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonicals.append(attrs["href"])


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    database = tmp_path_factory.mktemp("seo") / "seo.db"
    with TestClient(create_app(database_url=f"sqlite:///{database}")) as client:
        yield client


HELP_PAGES = {
    "quick-start": "Во время сбора можно закрыть вкладку.",
    "projects-and-queries": "Незакрытые кавычки вызовут ошибку импорта.",
    "scans": "Новый ручной запуск имеет собственный расчёт стоимости.",
    "schedule": "Отключение расписания не является командой остановки текущего запуска.",
    "reports": "относительный рост равен 50%",
    "answers-and-sources": "Сохраните полученный файл.",
    "billing": "Один промокод применяется один раз на аккаунт.",
    "troubleshooting": "Сам код присылать не нужно.",
}


def test_crawl_files_are_public_and_sitemap_lists_canonical_public_pages(client):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert robots.headers["content-type"].startswith("text/plain")
    assert "Sitemap: https://airate.tech/sitemap.xml" in robots.text
    parser = RobotFileParser()
    parser.parse(robots.text.splitlines())
    for bot in ("Googlebot", "Yandex", "bingbot"):
        for path in ("/", "/?utm_source=test", "/assets/brand/airate.svg", "/sitemap.xml", "/cabinet/", "/terms/", "/privacy/", "/help/", "/help/reports/"):
            assert parser.can_fetch(bot, path), (bot, path)
        assert not parser.can_fetch(bot, "/api/v1/control/projects")
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert sitemap.headers["content-type"].startswith("application/xml")
    root = ElementTree.fromstring(sitemap.content)
    assert [loc.text for loc in root.findall("{*}url/{*}loc")] == [
        "https://airate.tech/", *[f"https://airate.tech/help/{slug}/" for slug in HELP_PAGES],
    ]
    for path in ("/robots.txt", "/sitemap.xml"):
        head = client.head(path)
        assert head.status_code == 200 and not head.content
        assert head.headers["cache-control"] == "no-cache"


def test_homepage_ships_content_metadata_and_a_real_social_image(client):
    response = client.get("/?utm_source=test")
    assert response.status_code == 200
    assert "noindex" not in response.headers.get("x-robots-tag", "")
    html = response.text
    head = Head(html)
    assert head.canonicals == ["https://airate.tech/"]
    assert head.metas["robots"] == "index, follow, max-image-preview:large"
    assert all(name in head.metas["description"] for name in ("ChatGPT", "Perplexity", "Gemini", "Алисой", "Google AI Overview"))
    title = re.findall(r"<title>(.*?)</title>", html)
    assert title == [head.metas["og:title"]] == [head.metas["twitter:title"]]
    assert head.metas["description"] == head.metas["og:description"] == head.metas["twitter:description"]
    assert head.metas["og:url"] == "https://airate.tech/"
    assert head.metas["og:locale"] == "ru_RU"
    assert head.metas["twitter:card"] == "summary_large_image"
    assert head.metas["og:image"] == head.metas["twitter:image"]
    image = client.get(head.metas["og:image"].removeprefix("https://airate.tech"))
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image.content[16:24]) == (1200, 630)
    schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert schema["@type"] == "WebSite" and schema["name"] == "AIRate"
    assert schema["url"] == head.canonicals[0]
    assert len(re.findall(r"<h1\b", html)) == 1
    assert "Смотрите, где ИИ упоминает" in html and "Какие ИИ-системы доступны?" in html


def test_utility_pages_are_crawlable_but_not_indexable_and_unknown_pages_are_404(client):
    for path in ("/cabinet", "/cabinet/", "/cabinet/?register=1", "/terms", "/terms/", "/privacy", "/privacy/"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex, follow"
        assert not Head(response.text).canonicals
    for path in ("/missing-seo-page", "/news", "/sitemap.xml/extra"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("slug,body", HELP_PAGES.items())
def test_help_articles_ship_complete_public_content_and_metadata(client, slug, body):
    response = client.get(f"/help/{slug}/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "noindex" not in response.headers.get("x-robots-tag", "")
    html = response.text
    head = Head(html)
    assert head.metas["robots"] == "index, follow"
    assert head.canonicals == [f"https://airate.tech/help/{slug}/"]
    assert head.metas["og:url"] == head.canonicals[0]
    assert head.metas["description"] == head.metas["og:description"]
    assert re.findall(r"<title>(.*?)</title>", html) == [head.metas["og:title"]]
    assert len(re.findall(r"<h1\b", html)) == 1
    assert body in html
    assert "Не нашли ответ?" in html
    assert 'href="mailto:support@airate.tech"' in html
    assert 'href="/help/troubleshooting/"' in html
    assert client.get(f"/help/{slug}").status_code == 200


def test_help_aliases_and_unknown_paths(client):
    for path in ("/help", "/help/"):
        response = client.get(path)
        assert response.status_code == 200
        assert Head(response.text).canonicals == ["https://airate.tech/help/quick-start/"]
    for path in ("/help/no-such-article/", "/help/billing/extra", "/help/%2E%2E%2F.env", "/help/app.py"):
        assert client.get(path).status_code == 404


def test_help_search_index_is_public_and_contains_body_text(client):
    response = client.get("/assets/help-search.json")
    assert response.status_code == 200
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert "Незакрытые кавычки" in serialized
    assert "Последний день месяца" in serialized
    for slug in HELP_PAGES:
        assert f"/help/{slug}/" in serialized
