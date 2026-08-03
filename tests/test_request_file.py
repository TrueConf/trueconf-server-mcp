"""Tests for _request_file helper (B3): binary exports via MCP File with size guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.mcp import _request_file


@pytest.fixture
def _patch_access_token():
    """Patch get_access_token() to return a test AccessToken."""
    from fastmcp.server.auth import AccessToken

    at = AccessToken(token="tc-access-test", client_id="user-1", scopes=[])
    with patch("app.mcp.get_access_token", return_value=at):
        yield at


async def test_request_file_returns_file_on_success(
    mock_config_set,
    _patch_access_token,
) -> None:
    """A successful binary response returns a File content block."""
    from fastmcp.utilities.types import File

    binary_content = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    resp = httpx.Response(
        200,
        content=binary_content,
        headers={"content-type": "application/octet-stream"},
    )
    with patch("app.mcp._call_trueconf", side_effect=AsyncMock(return_value=resp)):
        result = await _request_file(
            "GET", "conferences/abc/ics", format="ics", name="abc.ics"
        )
    assert isinstance(result, File)
    assert result._format == "ics"


async def test_request_file_no_token_returns_auth_required(
    mock_config_set,
) -> None:
    """No access token → authorization_required dict."""
    with patch("app.mcp.get_access_token", return_value=None):
        result = await _request_file("GET", "conferences/abc/ics", format="ics")
    assert isinstance(result, dict)
    assert result["error"] == "authorization_required"


async def test_request_file_network_error_returns_dict(
    mock_config_set,
    _patch_access_token,
) -> None:
    """A ConnectError is caught and returned as a network_error dict."""
    raising = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with patch("app.mcp._call_trueconf", side_effect=raising):
        result = await _request_file("GET", "conferences/abc/ics", format="ics")
    assert isinstance(result, dict)
    assert result["error"] == "network_error"


async def test_request_file_401_refresh_then_retry_success(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Upstream 401 → refresh succeeds → retry returns File."""
    binary_content = b"col1,col2\r\nval1,val2\r\n"
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    resp_200 = httpx.Response(
        200, content=binary_content, headers={"content-type": "text/csv"}
    )
    mock_call = AsyncMock(side_effect=[resp_401, resp_200])
    mock_refresh = AsyncMock(return_value="tc-new-token")
    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request_file(
            "GET", "conferences/abc/messages-export", format="csv"
        )
    from fastmcp.utilities.types import File

    assert isinstance(result, File)
    assert result._format == "csv"
    assert mock_call.await_count == 2


async def test_request_file_401_refresh_fails_returns_token_invalid(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Upstream 401 → refresh fails → token_invalid dict."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    mock_call = AsyncMock(side_effect=[resp_401])
    mock_refresh = AsyncMock(return_value=None)
    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request_file("GET", "conferences/abc/ics", format="ics")
    assert isinstance(result, dict)
    assert result["error"] == "token_invalid"


async def test_request_file_too_large_returns_file_too_large_error(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Response larger than max_size returns a file_too_large error dict."""
    big_content = b"x" * 100
    resp = httpx.Response(
        200, content=big_content, headers={"content-type": "application/octet-stream"}
    )
    with patch("app.mcp._call_trueconf", side_effect=AsyncMock(return_value=resp)):
        result = await _request_file(
            "GET", "conferences/abc/ics", format="ics", max_size=50
        )
    assert isinstance(result, dict)
    assert result["error"] == "file_too_large"
    assert "100" in result["detail"]
    assert "50" in result["detail"]


async def test_request_file_at_size_boundary_returns_file(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Response exactly at max_size boundary returns File (not too_large)."""
    boundary_content = b"x" * 50
    resp = httpx.Response(
        200, content=boundary_content, headers={"content-type": "text/csv"}
    )
    with patch("app.mcp._call_trueconf", side_effect=AsyncMock(return_value=resp)):
        result = await _request_file(
            "GET", "conferences/abc/export", format="csv", max_size=50
        )
    from fastmcp.utilities.types import File

    assert isinstance(result, File)


async def test_request_file_non_401_error_returns_error_dict(
    mock_config_set,
    _patch_access_token,
) -> None:
    """A non-401 upstream error (e.g. 500) returns an error dict, not a File.

    Regression guard: _request_file must check is_error after the 401 refresh
    path, otherwise an HTML 500 body would be returned as a File content block.
    """
    resp = httpx.Response(
        500,
        text="<html>Internal Server Error</html>",
        headers={"content-type": "text/html"},
    )
    with patch("app.mcp._call_trueconf", side_effect=AsyncMock(return_value=resp)):
        result = await _request_file("GET", "conferences/abc/ics", format="ics")
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "HTTP 500"
