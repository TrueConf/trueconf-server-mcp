"""Tests for logging hygiene (T7): tokens masked at INFO, body only at DEBUG."""

from __future__ import annotations

import logging
from unittest.mock import patch

import httpx
import pytest
from fastmcp.server.auth import AccessToken

from app.mcp import _request, mask_token
from app.mcp.token_store import TokenStore


def test_mask_token_long() -> None:
    """Long tokens show first 6 and last 4 chars."""
    token = "abcdefghijklmnopqrstuvwxyz1234567890"
    masked = mask_token(token)
    assert masked.startswith("abcdef")
    assert masked.endswith("7890")
    assert "..." in masked
    assert token not in masked


def test_mask_token_short() -> None:
    """Short tokens are fully masked."""
    token = "short"
    masked = mask_token(token)
    assert token not in masked
    assert masked == "***"


def test_mask_token_medium() -> None:
    """Medium-length tokens still mask the middle."""
    token = "abcdefghij"  # 10 chars
    masked = mask_token(token)
    assert token not in masked
    assert masked.startswith("abcdef")
    assert masked.endswith("ghij")


async def test_request_info_log_excludes_body(
    mock_config_set, caplog: pytest.LogCaptureFixture
) -> None:
    """INFO logs from _call_trueconf must not contain the request body (PII)."""
    import app.mcp

    raw_token = "super-secret-trueconf-token-1234567890"
    at = AccessToken(token=raw_token, client_id="user-1", scopes=[])

    sensitive_body = {"topic": "secret-topic", "pin": "1234"}

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    mock_client = httpx.AsyncClient(
        base_url="https://server.example/api/v4",
        transport=httpx.MockTransport(_handler),
    )
    with (
        patch("app.mcp.get_access_token", return_value=at),
        patch.object(app.mcp, "_http_client", mock_client),
    ):
        with caplog.at_level(logging.DEBUG, logger="app.mcp"):
            await _request("POST", "conferences", json=sensitive_body)

    await mock_client.aclose()

    info_text = " ".join(r.message for r in caplog.records if r.levelno == logging.INFO)
    debug_text = " ".join(
        r.message for r in caplog.records if r.levelno == logging.DEBUG
    )
    # Body must NOT appear in INFO logs (PII leak)
    assert "secret-topic" not in info_text
    assert "1234" not in info_text
    # Body SHOULD appear in DEBUG logs (for debugging)
    assert "secret-topic" in debug_text
    # Token must NOT appear in any logs
    assert raw_token not in info_text
    assert raw_token not in debug_text


async def test_token_store_create_log_masks_token(
    mock_token_store: TokenStore, caplog: pytest.LogCaptureFixture
) -> None:
    """create_token INFO log must not contain the raw token value."""
    with caplog.at_level(logging.INFO, logger="app.mcp.token_store"):
        api_token = await mock_token_store.create_token(
            user_id="user-1",
            display_name="Tester",
            trueconf_access_token="tc-access",
            trueconf_refresh_token="tc-refresh",
            trueconf_expires_in=3600,
        )
    info_text = " ".join(r.message for r in caplog.records if r.levelno == logging.INFO)
    assert api_token.token not in info_text
