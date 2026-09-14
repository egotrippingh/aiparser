"""Скриншот целиком: и то, что не влезло в окно.

Firefox рисует только видимую часть, поэтому снимок высокого элемента выходит
наполовину чёрным (живая проверка Алисы 11.09.2026), а `full_page=True` на
страницах с внутренней прокруткой (Perplexity, чат Алисы) снимает пустую
обёртку вместо ответа. Рабочий способ один: прокручивать и снимать кусками, а
потом склеивать. Здесь это общее для всех адаптеров.
"""

from __future__ import annotations

import asyncio
import io
import logging

from PIL import Image

log = logging.getLogger("aiparser.adapters.shot")

# Потолок на число кусков: ответ бывает бесконечным (лента источников), а
# скриншот в 30 экранов никто читать не будет и в LLM он не влезет.
MAX_SLICES = 15
# Дать дорисоваться после прокрутки.
SETTLE_SEC = 0.3

# Геометрия элемента и его ближайшего прокручиваемого предка. Возвращаем
# видимое окно (с поправкой на липкие панели сверху и поле ввода снизу),
# полную высоту элемента и сам факт наличия внутреннего скроллера.
_GEOMETRY_JS = r"""(el, opts) => {
  const r = el.getBoundingClientRect();
  let sc = el.parentElement, scroller = null;
  while (sc) {
    const st = getComputedStyle(sc);
    if (/(auto|scroll)/.test(st.overflowY) && sc.scrollHeight > sc.clientHeight + 4) { scroller = sc; break }
    sc = sc.parentElement;
  }
  const view = scroller ? scroller.getBoundingClientRect() : null;
  let top = Math.max(0, view ? view.top : 0);
  let bottom = Math.min(innerHeight, view ? view.bottom : innerHeight);
  if (opts && opts.bottomSelector) {
    const b = document.querySelector(opts.bottomSelector);
    if (b) { const br = b.getBoundingClientRect(); if (br.top > top + 50) bottom = Math.min(bottom, br.top - 4) }
  }
  return {
    hasScroller: !!scroller, height: Math.ceil(r.height), width: Math.ceil(r.width),
    left: Math.floor(r.left), top: Math.floor(top), bottom: Math.floor(bottom),
    docScroll: !scroller,
  };
}"""

# Прокрутить так, чтобы верх элемента оказался на offset пикселей выше окна,
# и вернуть фактическое положение элемента после прокрутки.
_SCROLL_JS = r"""(el, arg) => {
  const target = el.getBoundingClientRect().top + (el.ownerDocument.defaultView.scrollY || 0);
  let sc = el.parentElement, scroller = null;
  while (sc) {
    const st = getComputedStyle(sc);
    if (/(auto|scroll)/.test(st.overflowY) && sc.scrollHeight > sc.clientHeight + 4) { scroller = sc; break }
    sc = sc.parentElement;
  }
  if (scroller) {
    const rel = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
    scroller.scrollTop = rel + arg.offset - arg.top;
  } else {
    scrollTo(0, target + arg.offset - arg.top);
  }
  const r = el.getBoundingClientRect();
  return { x: Math.floor(r.left), top: Math.floor(r.top), width: Math.ceil(r.width) };
}"""


async def full_shot(page, locator, *, bottom_selector: str | None = None, quality: int = 80) -> bytes:
    """Снимок элемента целиком. При любом сбое — снимок видимой части окна."""
    try:
        geo = await locator.evaluate(_GEOMETRY_JS, {"bottomSelector": bottom_selector})
        window_h = geo["bottom"] - geo["top"]
        if window_h < 1:
            return await page.screenshot(type="jpeg", quality=quality, full_page=False)
        if geo["height"] <= window_h:
            return await locator.screenshot(type="jpeg", quality=quality, timeout=8000)
        return await _stitch(page, locator, geo, quality)
    except Exception as exc:
        log.info("Скриншот элемента не снялся (%s) — снимаю окно", exc)
        return await page.screenshot(type="jpeg", quality=quality, full_page=False)


async def _stitch(page, locator, geo: dict, quality: int) -> bytes:
    total, slices, offset = geo["height"], [], 0.0
    while offset < total - 1 and len(slices) < MAX_SLICES:
        r = await locator.evaluate(_SCROLL_JS, {"offset": offset, "top": geo["top"]})
        await asyncio.sleep(SETTLE_SEC)
        y = max(geo["top"], r["top"] + offset)
        h = min(total - offset, geo["bottom"] - y)
        if h < 1:
            break
        slices.append(await page.screenshot(type="png", clip={"x": r["x"], "y": y, "width": r["width"], "height": h}))
        offset += h
    if len(slices) >= MAX_SLICES:
        log.info("Ответ длиннее %s экранов — снят верх", MAX_SLICES)
    return glue(slices, quality=quality)


def glue(parts: list[bytes], *, quality: int = 80) -> bytes:
    """Склеивает куски сверху вниз в один JPEG."""
    images = [Image.open(io.BytesIO(b)).convert("RGB") for b in parts if b]
    if not images:
        return b""
    out = Image.new("RGB", (max(i.width for i in images), sum(i.height for i in images)), "white")
    y = 0
    for im in images:
        out.paste(im, (0, y))
        y += im.height
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
