"""Tests for transcription MCP tools."""

from unittest.mock import patch

import pytest

from app.mcp.tools.trueconf_server_ai.transcriptions.get_transcription import get_transcription
from app.mcp.tools.trueconf_server_ai.transcriptions.get_transcription_lines import (
    get_transcription_lines,
)
from app.mcp.tools.trueconf_server_ai.transcriptions.get_transcription_summary import (
    get_transcription_summary,
)
from app.mcp.tools.trueconf_server_ai.transcriptions.list_transcriptions import list_transcriptions


@pytest.fixture
def _patch_ai_request():
    """Patch ai_request в модуле конкретного инструмента.

    Каждый tool-модуль делает `from app.mcp.auth.trueconf_server_ai import sai_request`,
    поэтому патчить нужно символ, импортированный в модуль инструмента,
    а не `app.mcp.auth.trueconf_server_ai.sai_request`.
    """
    from app.mcp.auth import trueconf_server_ai as ai_auth

    ai_auth.reset_ai_auth_cache()

    def _patch(module: str, return_value: dict, captured: dict):
        async def fake_sai_request(method, path, *, params=None):
            captured.update(method=method, path=path, params=params)
            return return_value

        return patch(f"{module}.sai_request", side_effect=fake_sai_request)

    yield _patch
    ai_auth.reset_ai_auth_cache()


async def test_list_transcriptions_passes_filters(_patch_ai_request):  # noqa: PT019 — fixture value used in body (patch factory)
    captured: dict = {}
    ctx = _patch_ai_request(
        "app.mcp.tools.trueconf_server_ai.transcriptions.list_transcriptions",
        {"ok": True},
        captured,
    )
    with ctx:
        result = await list_transcriptions(page=1, page_size=10, search="demo")
    assert result == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/user/v1/transcriptions"
    assert captured["params"] == {"page": 1, "page_size": 10, "search": "demo"}


async def test_get_transcription_builds_audio_url(_patch_ai_request, mock_config_set):  # noqa: PT019 — fixture value used in body (patch factory)
    mock_config_set.ai_server_url = "https://sai01t.trueconf.name"
    captured: dict = {}
    ctx = _patch_ai_request(
        "app.mcp.tools.trueconf_server_ai.transcriptions.get_transcription",
        {"id": 2, "transcription_url": "https://sai/t/2"},
        captured,
    )
    with ctx:
        result = await get_transcription(transcription_id=2)
    assert captured["path"] == "/api/user/v1/transcriptions/2"
    assert result["id"] == 2
    assert result["audio_url"] == ("https://sai01t.trueconf.name/api/user/v1/transcriptions/2/audio")


async def test_list_transcriptions_maps_sort_order(_patch_ai_request):  # noqa: PT019 — fixture value used in body (patch factory)
    async def _run(sort_order: str) -> dict:
        captured: dict = {}
        ctx = _patch_ai_request(
            "app.mcp.tools.trueconf_server_ai.transcriptions.list_transcriptions",
            {"ok": True},
            captured,
        )
        with ctx:
            result = await list_transcriptions(sort_field="started_at", sort_order=sort_order)
        assert result == {"ok": True}
        return captured["params"]

    assert await _run("desc") == {"sort_field": "started_at", "sort_order": 1}
    assert await _run("asc") == {"sort_field": "started_at", "sort_order": 0}


async def test_get_transcription_lines_passes_filters(_patch_ai_request):  # noqa: PT019 — fixture value used in body (patch factory)
    captured: dict = {}
    ctx = _patch_ai_request(
        "app.mcp.tools.trueconf_server_ai.transcriptions.get_transcription_lines",
        {"lines": []},
        captured,
    )
    with ctx:
        result = await get_transcription_lines(transcription_id=2, page=1, language="ru")
    assert result == {"lines": []}
    assert captured["path"] == "/api/user/v1/transcriptions/2/lines"
    assert captured["params"] == {"page": 1, "language": "ru"}


async def test_summary_empty_is_success(_patch_ai_request):  # noqa: PT019 — fixture value used in body (patch factory)
    """Пустой список саммари — нормальный ответ, не ошибка."""
    captured: dict = {}
    ctx = _patch_ai_request(
        "app.mcp.tools.trueconf_server_ai.transcriptions.get_transcription_summary",
        {"summaries": []},
        captured,
    )
    with ctx:
        result = await get_transcription_summary(transcription_id=2)
    assert result == {"summaries": []}
    assert captured["path"] == "/api/user/v1/transcriptions/2/summary"
