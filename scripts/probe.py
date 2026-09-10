"""Разведочный скрипт: открыть сервис в его собственном профиле приложения,
дампнуть HTML и ключевые структурные элементы. Не часть приложения —
используется только при написании адаптеров.

Использование:
  python scripts/probe.py <service_id> <url>
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.scanner.browser import service_context  # noqa: E402


async def main(service_id: str, url: str) -> None:
    async with service_context(service_id) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        summary = await page.evaluate(
            """() => {
                const els = document.querySelectorAll('[data-testid],[id],[contenteditable],[role],textarea,input');
                const out = [];
                els.forEach(n => {
                    if (out.length > 250) return;
                    const r = n.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) return;
                    out.push({
                        tag: n.tagName, id: n.id || null,
                        testid: n.getAttribute('data-testid'),
                        role: n.getAttribute('role'),
                        ce: n.getAttribute('contenteditable'),
                        ph: n.getAttribute('placeholder'),
                        cls: (n.className||'').toString().slice(0,90),
                        text: (n.textContent||'').trim().slice(0,50),
                    });
                });
                return out;
            }"""
        )

        out_dir = config.DATA_DIR / "probe"
        out_dir.mkdir(exist_ok=True)
        (out_dir / f"{service_id}_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (out_dir / f"{service_id}_page.html").write_text(await page.content(), encoding="utf-8")
        print(f"saved: {out_dir}/{service_id}_summary.json and _page.html")
        print(f"title: {await page.title()}")
        print(f"url: {page.url}")

        await asyncio.sleep(1)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
