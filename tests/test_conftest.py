"""Smoke tests proving the shared conftest fixtures work."""

from __future__ import annotations

from app.config import Config
from app.mcp.token_store import TokenStore


async def test_mock_config(mock_config: Config) -> None:
    """mock_config builds a valid Config with test defaults."""
    assert mock_config.server == "server.example"
    assert mock_config.verify_ssl is False
    assert mock_config.api_token_ttl == 3600


async def test_mock_token_store_create_and_read(
    mock_token_store: TokenStore,
) -> None:
    """mock_token_store can create and read back a token."""
    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access-test",
        trueconf_refresh_token="tc-refresh-test",
        trueconf_expires_in=3600,
    )
    assert api_token.token
    assert api_token.user_id == "user-1"

    fetched = await mock_token_store.get_by_token(api_token.token)
    assert fetched is not None
    assert fetched.trueconf_access_token == "tc-access-test"


def test_mock_httpx_response_json(mock_httpx_response) -> None:
    """mock_httpx_response builds a JSON httpx.Response."""
    resp = mock_httpx_response(status_code=200, json_data={"ok": True})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
