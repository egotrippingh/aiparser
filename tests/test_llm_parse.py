"""Разбор ответа модели: обрамление прощаем, обрывок — нет.

Живые прогоны 14.09.2026: сильные модели тратят почти весь лимит ответа на
внутреннее рассуждение и обрывают JSON на полуслове (finish_reason='length'),
а иногда заворачивают его в ```json-блок, хотя формат задан явно. Первое —
повод переспросить, второе — разобрать как есть.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detect.llm import parse_verdict  # noqa: E402

GOOD = '{"found": true, "mention_types": ["text"], "confidence": 0.9, "quote": "Геософт Дент", "reasoning": "назван в ответе"}'


def test_plain_json():
    v = parse_verdict(GOOD, "test/model")
    assert v and v.found and v.mention_types == ["text"] and v.confidence == 0.9
    assert v.quote == "Геософт Дент" and v.model == "test/model"


def test_markdown_wrapped_json():
    v = parse_verdict(f"```json\n{GOOD}\n```", "test/model")
    assert v and v.found and v.quote == "Геософт Дент"


def test_prose_around_json():
    v = parse_verdict(f"Вот мой ответ:\n{GOOD}\nНадеюсь, это помогло.", "test/model")
    assert v and v.found


def test_truncated_json_is_not_parsed():
    # Оборванный ответ — именно тот случай, ради которого сделан повтор:
    # принять его как «не найдено» значило бы тихо потерять проверку.
    assert parse_verdict('{"found": true, "mention_types": ["text", "link"], "confidence": 0.9', "m") is None


def test_garbage_and_empty():
    assert parse_verdict("", "m") is None
    assert parse_verdict(None, "m") is None
    assert parse_verdict("не могу ответить", "m") is None
    # JSON есть, но не наш: без поля found доверять ему нельзя.
    assert parse_verdict('{"ok": true}', "m") is None


def test_odd_types_do_not_crash():
    v = parse_verdict('{"found": 1, "confidence": "высокая", "mention_types": null}', "m")
    assert v and v.found and v.confidence == 0.0 and v.mention_types == []


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
