import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.scanner.adapters.base import AuthRequiredError, ServiceUnavailableError
from app.scanner.adapters.perplexity import PerplexityAdapter


def test_quota_heading_is_a_limit_not_a_missing_answer_or_retry():
    page = MagicMock()
    page.get_by_role.return_value.first.is_visible = AsyncMock(return_value=True)
    page.get_by_text.return_value.first.is_visible = AsyncMock(return_value=False)
    with pytest.raises(ServiceUnavailableError, match='лимит бесплатных поисков'):
        asyncio.run(PerplexityAdapter().capture(page))
    name = page.get_by_role.call_args.kwargs['name']
    assert name.fullmatch('Вы достигли лимита бесплатных поисков')
    assert not name.fullmatch('Ответ: Вы достигли лимита бесплатных поисков вчера')
    page.inner_text.assert_not_called()


def test_late_login_and_ordinary_answer_are_distinct():
    page = MagicMock()
    page.get_by_role.return_value.first.is_visible = AsyncMock(return_value=False)
    page.get_by_text.return_value.first.is_visible = AsyncMock(return_value=True)
    with pytest.raises(AuthRequiredError):
        asyncio.run(PerplexityAdapter()._raise_if_blocked(page))
    page.get_by_text.return_value.first.is_visible = AsyncMock(return_value=False)
    asyncio.run(PerplexityAdapter()._raise_if_blocked(page))
