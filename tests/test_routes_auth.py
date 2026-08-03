"""Tests for token delivery via httpOnly cookie (T8) and error codes (T9)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.mcp.routes import _handle_login_callback, _map_exception_to_code
from tests.conftest import FakeRequest


@pytest.fixture(autouse=True)
def _clear_completed_callbacks() -> None:
    """Keep the short-lived duplicate-callback cache isolated per test."""
    from app.mcp.routes import _CALLBACK_LOCKS, _COMPLETED_CALLBACKS

    _COMPLETED_CALLBACKS.clear()
    _CALLBACK_LOCKS.clear()


def test_map_exception_to_code_network():
    assert _map_exception_to_code(httpx.ConnectError("refused")) == "network_error"
    assert _map_exception_to_code(httpx.TimeoutException("slow")) == "network_error"


def test_map_exception_to_code_key_error():
    assert _map_exception_to_code(KeyError("access_token")) == "token_exchange_failed"


def test_map_exception_to_code_generic():
    assert _map_exception_to_code(RuntimeError("boom")) == "create_token_failed"


def test_error_page_renders_code_message(_init_i18n):
    """error_page maps the code to a human-readable i18n message."""
    from app.mcp.pages import error_page

    html_response = error_page(
        {"code": "token_exchange_failed"}, "en", "https://server.example"
    )
    body = html_response.body.decode()
    assert "exchange" in body.lower() or "token" in body.lower()
    # Raw exception text must not appear.
    assert "KeyError" not in body


def test_error_page_falls_back_when_no_code(_init_i18n):
    """error_page without a code falls back to the generic message."""
    from app.mcp.pages import error_page

    html_response = error_page({}, "en", "https://server.example")
    body = html_response.body.decode()
    assert "Something went wrong" in body


async def test_handle_login_callback_sets_cookie(
    mock_config_set, mock_token_store
) -> None:
    """On success, /auth/callback sets the cookie without a fetch redirect."""
    from app.mcp import set_token_store

    set_token_store(mock_token_store)

    token_resp = httpx.Response(
        200,
        json={
            "access_token": "tc-access",
            "refresh_token": "tc-refresh",
            "expires_in": 3600,
            "display_name": "Alice",
            "user_id": "user-1",
        },
    )

    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=token_resp)
    mock_http_client.get = AsyncMock(
        return_value=httpx.Response(
            200, json={"user": {"display_name": "Alice Smith"}}
        )
    )

    request = FakeRequest(query_params={"code": "test-code"})

    with patch("app.mcp.get_http_client", return_value=mock_http_client):
        response = await _handle_login_callback(request)

    assert response.status_code == 200
    assert "/success" in response.body.decode()
    # Cookie set with httpOnly + Secure (not no_tls) + SameSite=None.
    # SameSite=None is required because TrueConf Server's /oauth2/authorize
    # flow uses fetch() from JS — the callback is a cross-site cors request,
    # and SameSite=Lax would be dropped by the browser.
    set_cookie = response.headers.get("set-cookie", "")
    assert "mcp_token=" in set_cookie
    assert any(
        "mcp_login_pending=" in value
        for value in response.headers.getlist("set-cookie")
    )
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=none" in set_cookie

    # Verify the token-exchange request body (regression guard). The
    # OpenAPI spec says the field is `code`, but TrueConf Server currently
    # accepts `auth_code` — this assert locks the current behavior so a
    # future change to match the spec is deliberate, not accidental.
    mock_http_client.post.assert_awaited_once()
    call = mock_http_client.post.await_args
    assert call.args[0] == "oauth2/token"
    body = call.kwargs["json"]
    assert body["grant_type"] == "authorization_code"
    assert body["auth_code"] == "test-code"
    assert body["client_id"] == "test-client-id"
    assert body["client_secret"] == "test-secret"
    assert body["redirect_uri"].endswith("/auth/callback")
    mock_http_client.get.assert_awaited_once_with(
        "/me", headers={"Authorization": "Bearer tc-access"}, timeout=2.0
    )

    cookie_value = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    record = await mock_token_store.get_by_token(cookie_value)
    assert record is not None
    assert record.display_name == "Alice Smith"


async def test_handle_login_callback_uses_cached_token_for_duplicate_code(
    mock_config_set, mock_token_store
) -> None:
    """A repeated callback never exchanges a single-use OAuth code twice."""
    from app.mcp import set_token_store

    set_token_store(mock_token_store)
    token_resp = httpx.Response(
        200,
        json={"access_token": "tc-access", "user_id": "user-1"},
    )
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=token_resp)

    with patch("app.mcp.get_http_client", return_value=mock_http_client):
        first_response = await _handle_login_callback(
            FakeRequest(query_params={"code": "duplicate-code"})
        )
        second_response = await _handle_login_callback(
            FakeRequest(query_params={"code": "duplicate-code", "state": "null"})
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 302
    assert second_response.headers["location"].endswith("/success")
    assert "mcp_token=" in second_response.headers.get("set-cookie", "")
    mock_http_client.post.assert_awaited_once()


async def test_concurrent_login_callbacks_exchange_code_once(
    mock_config_set, mock_token_store
) -> None:
    """Concurrent delivery of one single-use code shares one exchange."""
    from app.mcp import set_token_store

    set_token_store(mock_token_store)
    token_resp = httpx.Response(
        200, json={"access_token": "tc-access", "user_id": "user-1"}
    )

    async def delayed_post(*args, **kwargs):
        await asyncio.sleep(0.02)
        return token_resp

    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(side_effect=delayed_post)

    with patch("app.mcp.get_http_client", return_value=mock_http_client):
        responses = await asyncio.gather(
            _handle_login_callback(FakeRequest(query_params={"code": "same-code"})),
            _handle_login_callback(FakeRequest(query_params={"code": "same-code"})),
        )

    assert sorted(response.status_code for response in responses) == [200, 302]
    mock_http_client.post.assert_awaited_once()


async def test_completed_callback_cache_is_reusable(
    mock_config_set, mock_token_store
) -> None:
    """Second and later duplicate callbacks reuse the same completed result."""
    from app.mcp import set_token_store

    set_token_store(mock_token_store)
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(
        return_value=httpx.Response(
            200, json={"access_token": "tc-access", "user_id": "user-1"}
        )
    )

    with patch("app.mcp.get_http_client", return_value=mock_http_client):
        responses = [
            await _handle_login_callback(
                FakeRequest(query_params={"code": "repeated-code"})
            )
            for _ in range(3)
        ]

    assert [response.status_code for response in responses] == [200, 302, 302]
    mock_http_client.post.assert_awaited_once()


async def test_handle_login_callback_without_code_redirects_to_login(
    mock_config_set,
) -> None:
    """/auth/callback without a code (and without an error) redirects to /
    instead of returning a blank 200 page."""
    request = FakeRequest(query_params={})
    response = await _handle_login_callback(request)
    assert response.status_code == 302
    location = response.headers.get("location", "")
    # Redirects to the login page (base URL root), not a blank 200.
    assert location.endswith("/") and "token=" not in location


async def test_handle_login_callback_exception_uses_code(mock_config_set) -> None:
    """An exception redirects to /error?code=create_token_failed (not ?error=str(e))."""
    request = FakeRequest(query_params={"code": "test-code"})

    with patch("app.mcp.get_http_client", side_effect=RuntimeError("boom")):
        response = await _handle_login_callback(request)

    assert response.status_code == 302
    location = response.headers.get("location", "")
    assert "code=create_token_failed" in location
    assert "boom" not in location


async def test_success_page_without_cookie_redirects(mock_config_set) -> None:
    """/success without the mcp_token cookie redirects to / for re-login."""
    from app.mcp.routes import success_page

    request = FakeRequest(cookies={}, query_params={})
    response = await success_page(request)
    assert response.status_code == 302
    assert "localhost" in response.headers.get("location", "")


async def test_success_page_with_cookie_renders_and_keeps_cookie(
    mock_config_set, mock_token_store
) -> None:
    """/success keeps its short-lived cookie for language re-rendering."""
    from app.mcp import set_token_store
    from app.mcp.routes import success_page

    # Create a token in the store so success_page can read display info.
    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Alice",
        trueconf_access_token="tc-access",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    set_token_store(mock_token_store)

    request = FakeRequest(cookies={"mcp_token": api_token.token}, query_params={})
    response = await success_page(request)

    # 200 (not redirect) and HTML body contains the token.
    assert response.status_code == 200
    body = response.body.decode()
    assert api_token.token in body
    # The original short-lived cookie remains available for a language switch.
    set_cookie = response.headers.get("set-cookie", "")
    assert "mcp_token" not in set_cookie


async def test_success_page_language_switch_keeps_token_cookie(
    mock_config_set, mock_token_store, _init_i18n
) -> None:
    """Changing language on /success does not send the visitor back to login."""
    from app.mcp import set_token_store
    from app.mcp.routes import success_page

    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Alice",
        trueconf_access_token="tc-access",
        trueconf_refresh_token=None,
        trueconf_expires_in=3600,
    )
    set_token_store(mock_token_store)

    response = await success_page(
        FakeRequest(cookies={"mcp_token": api_token.token}, query_params={"lang": "en"})
    )

    assert response.status_code == 200
    assert "tc_lang=en" in response.headers.get("set-cookie", "")


# ── CORS tests — cross-origin credentialed fetch() from TrueConf Server ──
#
# TrueConf Server's /oauth2/authorize flow uses fetch() with credentials,
# so /auth/callback is a credentialed cross-site request. The browser
# requires a specific Origin echo (not "*") + Allow-Credentials: true,
# otherwise it blocks the response and drops Set-Cookie → login loop.


async def test_handle_login_callback_echoes_origin_with_credentials(
    mock_config_set, mock_token_store
) -> None:
    """With a cross-origin Origin, /auth/callback echoes the Origin and sets
    Access-Control-Allow-Credentials: true — required for the browser to
    accept Set-Cookie on a credentialed fetch() response."""
    from app.mcp import set_token_store

    set_token_store(mock_token_store)

    token_resp = httpx.Response(
        200,
        json={
            "access_token": "tc-access",
            "refresh_token": "tc-refresh",
            "expires_in": 3600,
            "display_name": "Alice",
            "user_id": "user-1",
        },
    )
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=token_resp)

    request = FakeRequest(
        query_params={"code": "test-code"},
        headers={"origin": "https://server.example"},
    )

    with patch("app.mcp.get_http_client", return_value=mock_http_client):
        response = await _handle_login_callback(request)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"
    # Cookie is still set (CORS echo + credentials allow Set-Cookie to stick).
    assert "mcp_token=" in response.headers.get("set-cookie", "")


async def test_handle_login_callback_no_origin_returns_wildcard(
    mock_config_set, mock_token_store
) -> None:
    """Without an Origin header (same-origin or direct request), _cors()
    returns Access-Control-Allow-Origin: * and omits Allow-Credentials."""
    from app.mcp import set_token_store

    set_token_store(mock_token_store)

    token_resp = httpx.Response(
        200,
        json={
            "access_token": "tc-access",
            "refresh_token": "tc-refresh",
            "expires_in": 3600,
            "display_name": "Alice",
            "user_id": "user-1",
        },
    )
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=token_resp)

    request = FakeRequest(query_params={"code": "test-code"})

    with patch("app.mcp.get_http_client", return_value=mock_http_client):
        response = await _handle_login_callback(request)

    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers
    assert "vary" not in response.headers


async def test_cors_rejects_untrusted_origin(mock_config_set) -> None:
    """Credentialed CORS headers are emitted only for configured origins."""
    request = FakeRequest(
        query_params={"error": "access_denied"},
        headers={"origin": "https://evil.example"},
    )

    response = await _handle_login_callback(request)

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


async def test_handle_login_callback_error_branch_echoes_origin(
    mock_config_set,
) -> None:
    """The ?error=... redirect branch must also echo Origin + credentials."""
    request = FakeRequest(
        query_params={"error": "access_denied"},
        headers={"origin": "https://server.example"},
    )
    response = await _handle_login_callback(request)

    assert response.status_code == 302
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_handle_login_callback_no_code_echoes_origin(mock_config_set) -> None:
    """The no-code redirect branch must echo Origin + credentials."""
    request = FakeRequest(
        query_params={},
        headers={"origin": "https://server.example"},
    )
    response = await _handle_login_callback(request)

    assert response.status_code == 302
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_success_page_options_preflight_cors(mock_config_set) -> None:
    """OPTIONS /success returns 204 with CORS echo + Allow-Credentials."""
    from app.mcp.routes import success_page

    request = FakeRequest(
        method="OPTIONS",
        headers={"origin": "https://server.example"},
    )
    response = await success_page(request)

    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"


async def test_success_page_with_cookie_echoes_origin(
    mock_config_set, mock_token_store, _init_i18n
) -> None:
    """GET /success with cookie + Origin renders 200 with CORS echo."""
    from app.mcp import set_token_store
    from app.mcp.routes import success_page

    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Alice",
        trueconf_access_token="tc-access",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    set_token_store(mock_token_store)

    request = FakeRequest(
        cookies={"mcp_token": api_token.token},
        query_params={},
        headers={"origin": "https://server.example"},
    )
    response = await success_page(request)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"


async def test_login_page_echoes_origin(mock_config_set, _init_i18n) -> None:
    """GET / with Origin returns 200 with CORS echo + Allow-Credentials."""
    from app.mcp.routes import login_page

    request = FakeRequest(headers={"origin": "https://server.example"})
    response = await login_page(request)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"


async def test_error_page_echoes_origin(mock_config_set, _init_i18n) -> None:
    """GET /error with Origin returns 400 (error page) with CORS echo."""
    from app.mcp.routes import error_page

    request = FakeRequest(
        query_params={},
        headers={"origin": "https://server.example"},
    )
    response = await error_page(request)

    # error_page renders with status_code=400 (it's an error page).
    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == "https://server.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"


async def test_login_page_with_pending_marker_redirects_to_success(
    mock_config_set,
) -> None:
    """The one-shot post-callback marker redirects / to /success."""
    from app.mcp.routes import login_page

    request = FakeRequest(
        cookies={"mcp_token": "some-token", "mcp_login_pending": "1"},
        query_params={},
    )
    response = await login_page(request)

    assert response.status_code == 302
    assert "/success" in response.headers.get("location", "")
    set_cookie = response.headers.get("set-cookie", "")
    assert "mcp_login_pending" in set_cookie
    assert "Max-Age=0" in set_cookie


async def test_login_page_with_only_token_cookie_shows_login(
    mock_config_set, _init_i18n
) -> None:
    """After /success consumes the marker, visiting / shows login."""
    from app.mcp.routes import login_page

    response = await login_page(
        FakeRequest(cookies={"mcp_token": "some-token"}, query_params={})
    )

    assert response.status_code == 200
    assert "oauth2/authorize" in response.body.decode()


async def test_login_page_without_cookie_shows_login_form(
    mock_config_set, _init_i18n
) -> None:
    """GET / without mcp_token cookie renders the login form (not a redirect)."""
    from app.mcp.routes import login_page

    request = FakeRequest(cookies={}, query_params={})
    response = await login_page(request)

    assert response.status_code == 200
    assert "oauth2/authorize" in response.body.decode()
