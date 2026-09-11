"""Параллельный скан: разные ИИ-системы идут одновременно, если это включено в проекте.

Настоящий браузер здесь не нужен: оркестратору подсовываются ненастоящие
адаптеры и браузерный контекст, у которых «ответ» занимает долю секунды.
Проверяется ровно то, за что отвечает оркестратор:
  * с включённым parallel_scan очереди сервисов пересекаются во времени;
  * без него сервисы идут строго по очереди;
  * внутри одного сервиса запросы всегда по одному;
  * результаты всех пар «запрос × сервис» записаны.

Работает на временной БД — данные пользователя не трогает.
"""

import asyncio
import io
import sys
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp = Path(tempfile.mkdtemp(prefix="aiparser_parallel_"))

from app import config  # noqa: E402

config.DB_PATH = _tmp / "test.db"
config.SCREENSHOTS_DIR = _tmp / "shots"

from PIL import Image  # noqa: E402

from app.db import repo  # noqa: E402
from app.scanner import orchestrator  # noqa: E402
from app.scanner.adapters.base import Capture, ReadyState  # noqa: E402

repo.init_db()

SERVICES = ["chatgpt", "perplexity"]
ANSWER_SEC = 0.15


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


class Journal:
    """Кто когда отвечал и сколько сервисов шло одновременно."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float, float]] = []
        self.max_running = 0
        self.busy: dict[str, bool] = {}
        self.overlap_inside_service = False


journal = Journal()


class FakePage:
    def is_closed(self) -> bool:
        return False


class FakeContext:
    def __init__(self) -> None:
        self.pages = [FakePage()]

    async def new_page(self) -> FakePage:
        return FakePage()


@asynccontextmanager
async def fake_service_context(service_id: str, **_):
    yield FakeContext()


class FakeAdapter:
    def __init__(self, service_id: str) -> None:
        self.service_id = service_id

    async def ensure_ready(self, page) -> ReadyState:
        return ReadyState(ok=True)

    async def ask(self, page, query: str, region, *, speed: float) -> None:
        if journal.busy.get(self.service_id):
            journal.overlap_inside_service = True
        journal.busy[self.service_id] = True
        ctl = orchestrator.active_controller()
        journal.max_running = max(journal.max_running, len(ctl.running) if ctl else 0)
        start = time.monotonic()
        await asyncio.sleep(ANSWER_SEC)
        journal.calls.append((self.service_id, start, time.monotonic()))
        journal.busy[self.service_id] = False

    async def capture(self, page) -> Capture:
        return Capture(screenshot_bytes=PNG, answer_text="Лучший поставщик — Тестбренд.", sources=[])


async def _no_pause(*_, **__) -> None:
    return None


orchestrator.service_context = fake_service_context
orchestrator.get_adapter = lambda sid: FakeAdapter(sid)
orchestrator.humanize.between_queries = _no_pause


_n = 0


def _run(parallel: bool) -> tuple[int, Journal]:
    global journal, _n
    journal = Journal()
    _n += 1
    pid = repo.create_project(f"Параллель {_n}", "Тестбренд", parallel_scan=parallel)
    repo.add_queries(pid, ["запрос один", "запрос два", "запрос три"])

    async def main() -> int:
        scan_id = await orchestrator.start_scan(pid, SERVICES)
        deadline = time.monotonic() + 15
        while orchestrator.get_controller(scan_id) is not None:
            assert time.monotonic() < deadline, "скан не завершился за 15 секунд"
            await asyncio.sleep(0.02)
        return scan_id

    return asyncio.run(main()), journal


def _span(j: Journal, service: str) -> tuple[float, float]:
    mine = [c for c in j.calls if c[0] == service]
    return min(c[1] for c in mine), max(c[2] for c in mine)


def test_parallel_services_overlap():
    scan_id, j = _run(parallel=True)
    (a0, a1), (b0, b1) = _span(j, "chatgpt"), _span(j, "perplexity")
    assert a0 < b1 and b0 < a1, f"очереди не пересеклись: {a0, a1} и {b0, b1}"
    assert j.max_running == 2
    assert not j.overlap_inside_service, "внутри одного сервиса два запроса шли разом"
    rows = repo.results_for_scan(scan_id)
    assert len(rows) == 6 and all(r["status"] == "found" for r in rows)
    assert repo.get_scan(scan_id)["status"] == "done"


def test_sequential_by_default():
    scan_id, j = _run(parallel=False)
    (a0, a1), (b0, b1) = _span(j, "chatgpt"), _span(j, "perplexity")
    assert a1 <= b0 or b1 <= a0, "без parallel_scan сервисы не должны пересекаться"
    assert j.max_running == 1
    assert len(repo.results_for_scan(scan_id)) == 6


def test_parallel_is_faster():
    started = time.monotonic()
    _run(parallel=True)
    par = time.monotonic() - started
    started = time.monotonic()
    _run(parallel=False)
    seq = time.monotonic() - started
    # 3 запроса × 2 сервиса по 0.15 с: по очереди ≈ 0.9 с, параллельно ≈ 0.45 с.
    assert par < seq * 0.8, f"параллельно {par:.2f} с, по очереди {seq:.2f} с"


def _ctl_with(parallel: bool, now: float) -> "orchestrator.ScanController":
    # Google: 10 из 20 за 100 с (10 с на запрос), Perplexity: 2 из 20 за 100 с (50 с).
    ctl = orchestrator.ScanController(0, 0, total=40, scan_date="2026-09-11")
    ctl.started_at = now - 100
    ctl.parallel = parallel
    ctl.per_service = {
        "google_aio": {"done": 10, "total": 20, "started": now - 100},
        "perplexity": {"done": 2, "total": 20, "started": now - 100},
    }
    ctl.done = 12
    return ctl


def test_eta_counts_each_service_separately():
    now = time.time()
    # Параллельно ждём самого медленного: Perplexity, 18 × 50 с. Общая средняя
    # (12 за 100 с × 28 оставшихся ≈ 233 с) занижала прогноз вчетверо.
    assert _ctl_with(True, now)._eta(now) == 900
    # По очереди — сумма: 10 × 10 с + 18 × 50 с.
    assert _ctl_with(False, now)._eta(now) == 1000


def test_eta_for_service_without_results_uses_overall_speed():
    now = time.time()
    ctl = _ctl_with(False, now)
    ctl.per_service["alice"] = {"done": 0, "total": 6, "started": None}
    ctl.total = 46
    # Алиса ещё не начиналась: 6 × (100 с / 12) = 50 с сверх прежних 1000.
    assert ctl._eta(now) == 1050


def test_snapshot_has_per_service_progress():
    ctl = _ctl_with(True, time.time())
    ctl.advance("perplexity")
    snap = ctl.snapshot()
    assert snap["services"] == {"google_aio": {"done": 10, "total": 20}, "perplexity": {"done": 3, "total": 20}}
    assert snap["done"] == 13


def test_project_flag_roundtrip_and_migration():
    pid = repo.create_project("Флаг", "Бренд")
    assert repo.get_project(pid)["parallel_scan"] is False
    repo.update_project(pid, parallel_scan=True)
    assert repo.get_project(pid)["parallel_scan"] is True

    # Старая база без колонки: init_db должен её добавить, не трогая данные.
    import sqlite3

    old = _tmp / "old.db"
    c = sqlite3.connect(old)
    c.execute("""CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                 brand_name TEXT NOT NULL, brand_aliases_json TEXT NOT NULL DEFAULT '[]',
                 brand_domains_json TEXT NOT NULL DEFAULT '[]', region_code TEXT,
                 deep_check_depth INTEGER NOT NULL DEFAULT 0, notes TEXT,
                 created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    c.execute("INSERT INTO projects (name, brand_name) VALUES ('старый', 'Бренд')")
    c.commit()
    c.close()
    repo._migrate(sqlite3.connect(old))
    c = sqlite3.connect(old)
    cols = {r[1] for r in c.execute("PRAGMA table_info(projects)")}
    assert "parallel_scan" in cols
    assert c.execute("SELECT name, parallel_scan FROM projects").fetchall() == [("старый", 0)]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
