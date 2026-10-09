from __future__ import annotations

from app.scanner.adapters.alice import AliceAdapter
from app.scanner.adapters.base import SearchAdapter
from app.scanner.adapters.chatgpt import ChatGPTAdapter
from app.scanner.adapters.google_aio import GoogleAIOAdapter
from app.scanner.adapters.perplexity import PerplexityAdapter
from app.scanner.adapters.xmlriver import XMLRiverAdapter

ADAPTERS: dict[str, SearchAdapter] = {
    a.service_id: a for a in [PerplexityAdapter(), AliceAdapter(), ChatGPTAdapter(), GoogleAIOAdapter(),
                              XMLRiverAdapter("yandex_neuro", {})]
}


def get_adapter(service_id: str) -> SearchAdapter:
    try:
        return ADAPTERS[service_id]
    except KeyError:
        raise ValueError(
            f"Адаптер для «{service_id}» ещё не реализован. Готово: {list(ADAPTERS)}"
        ) from None
