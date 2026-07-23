from unittest.mock import AsyncMock, Mock

import pytest

from app.db import session as session_module


@pytest.mark.asyncio
async def test_dispose_engine_resets_cached_resources(monkeypatch):
    engine = Mock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_session_factory", Mock())

    await session_module.dispose_engine()

    engine.dispose.assert_awaited_once()
    assert session_module._engine is None
    assert session_module._session_factory is None


@pytest.mark.asyncio
async def test_dispose_engine_is_safe_before_initialization(monkeypatch):
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_session_factory", None)
    await session_module.dispose_engine()
    assert session_module._engine is None
