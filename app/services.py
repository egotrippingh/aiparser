"""Реестр поддерживаемых ИИ-источников.

Один список на всё приложение: по нему строятся колонки таблицы, вкладки в
карточке запроса, кнопки входа в настройках и очередь сканирования. Добавление
нового источника — строка здесь плюс файл адаптера.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceInfo:
    id: str
    name: str
    short: str
    requires_auth: bool  # подсказка для UI («обычно нужен вход»), не гарантия.
    login_url: str
    color: str
    note: str = ""

    # `requires_auth` — это ТОЛЬКО начальная метка для интерфейса (иконка на
    # карточке сервиса в настройках). Любой сервис в любой момент может
    # свалиться в auth_required — сайты меняют политику анонимного доступа
    # без предупреждения (так и оказалось с Perplexity: 28.08.2026 анонимная
    # сессия перестала показывать ответ и потребовала регистрацию). Поэтому
    # кнопка «Войти» в настройках показывается для ВСЕХ сервисов
    # безусловно, а фактическую необходимость входа определяет исполнение
    # ensure_ready() у адаптера, а не это поле.


SERVICES: tuple[ServiceInfo, ...] = (
    ServiceInfo(
        id="perplexity",
        name="Perplexity",
        short="PPLX",
        requires_auth=True,
        login_url="https://www.perplexity.ai/",
        color="--c2",
        note="Анонимная сессия иногда позволяет один запрос, но обычно требует вход.",
    ),
    ServiceInfo(
        id="chatgpt",
        name="ChatGPT",
        short="GPT",
        requires_auth=True,
        login_url="https://chatgpt.com/",
        color="--c1",
        note="Нужен вход. Каждый запрос — в новом чате, чтобы контекст не влиял на ответ.",
    ),
    ServiceInfo(
        id="yandex_neuro",
        name="Яндекс Нейро",
        short="Нейро",
        requires_auth=False,
        login_url="https://ya.ru/",
        color="--c3",
        note=(
            "Блок нейроответа в выдаче ya.ru. Регион — параметром lr. "
            "28.08.2026: даже с Яндекс-логином через Алису (разные домены, "
            "кука не переехала) hasSearchNeuroTab оставался false — похоже, "
            "тег нужен именно логин НА ya.ru, а не любой Яндекс-аккаунт. "
            "Если после входа тег не появляется — это не баг адаптера, а "
            "показ блока сам по себе; статус будет skipped, как у Google AIO."
        ),
    ),
    ServiceInfo(
        id="alice",
        name="Алиса AI",
        short="Алиса",
        requires_auth=True,
        login_url="https://alice.yandex.ru/",
        color="--c4",
        note="Отдельный чат Алисы, нужен вход в аккаунт Яндекса.",
    ),
    ServiceInfo(
        id="google_aio",
        name="Google AI Overview",
        short="Google AIO",
        requires_auth=False,
        login_url="https://www.google.com/",
        color="--c5",
        note="AI-блок в выдаче Google. Показывается не по всем запросам; из РФ обычно нужен VPN.",
    ),
)

BY_ID = {s.id: s for s in SERVICES}
ALL_IDS = [s.id for s in SERVICES]


def get(service_id: str) -> ServiceInfo:
    try:
        return BY_ID[service_id]
    except KeyError:
        raise ValueError(f"Неизвестный сервис: {service_id}") from None
