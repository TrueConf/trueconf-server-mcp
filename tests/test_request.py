"""Tests for _request resilience (T5): network errors, upstream 401 retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.mcp import _request


@pytest.fixture
def _patch_access_token():
    """Patch get_access_token() to return a test AccessToken."""
    from fastmcp.server.auth import AccessToken

    at = AccessToken(token="tc-access-test", client_id="user-1", scopes=[])
    with patch("app.mcp.get_access_token", return_value=at):
        yield at


async def test_network_error_returns_dict(
    mock_config_set,
    _patch_access_token,
) -> None:
    """A ConnectError is caught and returned as a network_error dict."""
    raising = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with patch("app.mcp._call_trueconf", side_effect=raising):
        result = await _request("GET", "conferences")
    assert result["error"] == "network_error"
    assert "connection refused" in result["detail"]


async def test_timeout_returns_network_error_dict(
    mock_config_set,
    _patch_access_token,
) -> None:
    """A TimeoutException is caught as a network_error."""
    raising = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    with patch("app.mcp._call_trueconf", side_effect=raising):
        result = await _request("GET", "conferences")
    assert result["error"] == "network_error"


async def test_upstream_401_refresh_then_retry_success(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Upstream 401 → refresh succeeds → retry returns the real response."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    resp_200 = httpx.Response(200, json={"ok": True})

    mock_call = AsyncMock(side_effect=[resp_401, resp_200])
    mock_refresh = AsyncMock(return_value="tc-new-token")

    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request("GET", "conferences")

    assert result == {"ok": True}
    assert mock_call.await_count == 2
    mock_refresh.assert_awaited_once_with("tc-access-test")


async def test_upstream_401_refresh_fails_returns_token_invalid(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Upstream 401 → refresh fails → token_invalid dict with login_url."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    mock_call = AsyncMock(side_effect=[resp_401])
    mock_refresh = AsyncMock(return_value=None)

    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request("GET", "conferences")

    assert result["error"] == "token_invalid"
    assert "login_url" in result
    assert mock_call.await_count == 1


async def test_upstream_401_after_retry_returns_token_invalid(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Upstream 401 → refresh succeeds → retry also 401 → token_invalid."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    resp_401_again = httpx.Response(401, json={"error": "still unauthorized"})
    mock_call = AsyncMock(side_effect=[resp_401, resp_401_again])
    mock_refresh = AsyncMock(return_value="tc-new-token")

    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request("GET", "conferences")

    assert result["error"] == "token_invalid"
    assert mock_call.await_count == 2


async def test_no_token_returns_auth_required(mock_config_set) -> None:
    """No access token → authorization_required dict (existing behaviour)."""
    with patch("app.mcp.get_access_token", return_value=None):
        result = await _request("GET", "conferences")
    assert result["error"] == "authorization_required"
    assert "login_url" in result


async def test_network_error_on_retry_returns_network_error(
    mock_config_set,
    _patch_access_token,
) -> None:
    """Upstream 401 → refresh succeeds → retry hits network error → network_error."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    mock_call = AsyncMock(
        side_effect=[resp_401, httpx.ConnectError("retry connection refused")]
    )
    mock_refresh = AsyncMock(return_value="tc-new-token")

    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request("GET", "conferences")

    assert result["error"] == "network_error"


async def test_token_invalid_includes_how_to(
    mock_config_set,
) -> None:
    """token_invalid dict includes how_to key (was missing)."""
    from app.mcp import _token_invalid_dict

    result = _token_invalid_dict()
    assert "how_to" in result
    assert "login_url" in result
    assert "message" in result


async def test_token_invalid_message_does_not_claim_revoked(
    mock_config_set,
) -> None:
    """token_invalid message must not claim the TrueConf token was revoked.

    Regression: when OUR api token merely expired (api_token_ttl elapsed) and
    the refresh path fails, the user was told "TrueConf token revoked" — the
    TrueConf token was never revoked. The message must cover expiry too.
    """
    from app.mcp import _token_invalid_dict

    result = _token_invalid_dict()
    assert "TrueConf token revoked" not in result["message"]
    assert "expired" in result["message"]


async def test_try_refresh_exception_returns_token_invalid(
    mock_config_set,
    _patch_access_token,
) -> None:
    """_try_refresh_trueconf_token raising → token_invalid dict (not 500)."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    mock_call = AsyncMock(side_effect=[resp_401])

    async def _raising_refresh(_token):
        raise RuntimeError("disk I/O error")

    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=_raising_refresh),
    ):
        result = await _request("GET", "conferences")

    assert result["error"] == "token_invalid"
    assert "login_url" in result


def test_parse_response_null_json_returns_empty_dict() -> None:
    """_parse_response with upstream JSON null returns {} (not None)."""
    from app.mcp import _parse_response

    resp = httpx.Response(
        200, content=b"null", headers={"content-type": "application/json"}
    )
    result = _parse_response(resp)
    assert result == {}


def test_parse_response_json_array_returns_data_dict() -> None:
    """_parse_response with upstream JSON array wraps in {"data": [...]}."""
    from app.mcp import _parse_response

    resp = httpx.Response(
        200,
        content=b'[{"id": 1}, {"id": 2}]',
        headers={"content-type": "application/json"},
    )
    result = _parse_response(resp)
    assert result == {"data": [{"id": 1}, {"id": 2}]}


def test_handle_error_non_json_includes_body_context() -> None:
    """Non-JSON upstream error includes first 500 chars of body as detail.

    Regression guard: previously a non-JSON 5xx (e.g. HTML error page) was
    reduced to ``{"error": "HTTP 500"}`` with no body, making production
    incidents undebuggable. The fix adds ``detail=response.text[:500]``.
    """
    from app.mcp import _handle_error

    body = "<html><body>500 Internal Server Error: upstream DB down</body></html>"
    resp = httpx.Response(500, text=body, headers={"content-type": "text/html"})
    result = _handle_error(resp)
    assert result["error"] == "HTTP 500"
    assert result["status_code"] == 500
    assert "detail" in result, "non-JSON error must include body context"
    assert "Internal Server Error" in result["detail"]
    assert len(result["detail"]) <= 500


def test_handle_error_non_json_truncates_long_body() -> None:
    """Non-JSON error body is truncated to 500 chars to bound error size."""
    from app.mcp import _handle_error

    body = "x" * 5000
    resp = httpx.Response(502, text=body, headers={"content-type": "text/plain"})
    result = _handle_error(resp)
    assert result["error"] == "HTTP 502"
    assert result["status_code"] == 502
    assert len(result["detail"]) == 500


async def test_init_http_client_uses_v4_api_base(mock_config_set) -> None:
    """init_http_client строит клиент на базе /api/v4 из конфига."""
    import app.mcp

    await app.mcp.close_http_client()
    try:
        app.mcp.init_http_client()
        client = app.mcp.get_http_client()
        assert str(client.base_url) == "https://server.example/api/v4/"
    finally:
        await app.mcp.close_http_client()


async def test_request_version_override_builds_v4_1_url(
    mock_config_set, _patch_access_token
) -> None:
    """_request with version='v4.1' targets the v4.1 API base as an absolute URL."""
    captured: dict = {}

    async def _capture(method, path, token, **kwargs):
        captured["path"] = path
        return httpx.Response(200, json={})

    with patch("app.mcp._call_trueconf", side_effect=_capture):
        await _request("GET", "users/user-1/addressbook", version="v4.1")

    assert (
        captured["path"] == "https://server.example/api/v4.1/users/user-1/addressbook"
    )


async def test_request_v4_1_404_returns_endpoint_not_supported(
    mock_config_set, _patch_access_token
) -> None:
    """A v4.1 request returning 404 → endpoint_not_supported (server < 5.5.6)."""
    resp_404 = httpx.Response(
        404,
        json={
            "error": {
                "code": 404,
                "message": "Not Found",
                "trace_id": "3904405107",
                "errors": [{"reason": "routeNotFound"}],
            }
        },
    )
    with patch("app.mcp._call_trueconf", side_effect=AsyncMock(return_value=resp_404)):
        result = await _request("GET", "users/user-1/addressbook", version="v4.1")

    assert result["error"] == "endpoint_not_supported"
    assert result["detail"] == "HTTP 404"
    assert "5.5.6" in result["message"]
    assert "how_to" in result


async def test_request_404_without_version_returns_normal_error(
    mock_config_set, _patch_access_token
) -> None:
    """A plain 404 (no version override) keeps the normal error handling."""
    resp_404 = httpx.Response(
        404,
        json={
            "error": {
                "code": 404,
                "message": "Not Found",
                "errors": [{"reason": "routeNotFound"}],
            }
        },
    )
    with patch("app.mcp._call_trueconf", side_effect=AsyncMock(return_value=resp_404)):
        result = await _request("GET", "conferences/nope")

    assert result["error"] != "endpoint_not_supported"
    assert "how_to" not in result


async def test_request_v4_1_404_after_401_retry_returns_endpoint_not_supported(
    mock_config_set, _patch_access_token
) -> None:
    """401 → refresh → retry returns 404 → still endpoint_not_supported."""
    resp_401 = httpx.Response(401, json={"error": "unauthorized"})
    resp_404 = httpx.Response(
        404,
        json={
            "error": {
                "code": 404,
                "message": "Not Found",
                "errors": [{"reason": "routeNotFound"}],
            }
        },
    )
    mock_call = AsyncMock(side_effect=[resp_401, resp_404])
    mock_refresh = AsyncMock(return_value="tc-new-token")

    with (
        patch("app.mcp._call_trueconf", side_effect=mock_call),
        patch("app.mcp._try_refresh_trueconf_token", side_effect=mock_refresh),
    ):
        result = await _request("GET", "users/user-1/addressbook", version="v4.1")

    assert result["error"] == "endpoint_not_supported"
    assert mock_call.await_count == 2
