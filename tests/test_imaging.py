"""Подготовка скриншота для модели: высокий снимок режется на куски.

С 14.09.2026 адаптеры снимают ответ целиком, и у Perplexity это бывает 9000
пикселей в высоту (живая проверка: 1104×9393). Одной картинкой такое слать
бессмысленно — модель ужмёт её до нечитаемого текста.
"""

import io
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app import imaging  # noqa: E402


def _shot(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), "white")
    for y in range(0, height, 50):          # полосы, чтобы куски отличались друг от друга
        for x in range(width):
            img.putpixel((x, min(y + (x % 3), height - 1)), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=80)
    return buf.getvalue()


def _size(b: bytes) -> tuple[int, int]:
    im = Image.open(io.BytesIO(b))
    return im.width, im.height


def test_short_shot_stays_one_image():
    parts = imaging.for_llm(_shot(1100, 900))
    assert len(parts) == 1
    w, h = _size(parts[0])
    assert w == 1000 and h == 818          # ужат по ширине, пропорции сохранены


def test_tall_shot_is_cut_into_parts():
    parts = imaging.for_llm(_shot(1104, 9393), chunk=2500, max_parts=3)
    assert len(parts) == 3
    assert all(_size(p)[0] == 1000 for p in parts)
    assert all(_size(p)[1] <= 2500 for p in parts)


def test_cut_keeps_head_middle_and_tail():
    # Ровно 4 куска — берём первый, средний и последний: хвост с источниками
    # иначе никогда не попадал бы модели на глаза. Полосы разного цвета
    # показывают, откуда взят каждый кусок (сравнивать пиксели дословно
    # нельзя: WebP сжимает с потерями).
    bands = [(220, 20, 20), (20, 200, 20), (20, 20, 220), (230, 210, 30)]
    img = Image.new("RGB", (1000, 10000))
    for i, color in enumerate(bands):
        img.paste(color, (0, i * 2500, 1000, (i + 1) * 2500))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=90)

    parts = imaging.for_llm(buf.getvalue(), chunk=2500, max_parts=3)
    assert [_size(p)[1] for p in parts] == [2500, 2500, 2500]
    got = [Image.open(io.BytesIO(p)).convert("RGB").getpixel((500, 1250)) for p in parts]
    for actual, expected in zip(got, [bands[0], bands[2], bands[3]]):
        assert all(abs(a - e) < 30 for a, e in zip(actual, expected)), (got, bands)


def test_narrow_shot_is_not_upscaled():
    parts = imaging.for_llm(_shot(600, 400))
    assert _size(parts[0]) == (600, 400)


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
