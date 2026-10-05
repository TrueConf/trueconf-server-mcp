"""Tests for app.mcp.auth.trueconf_server_ai (exchange, cache, refresh-on-401)."""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.server.auth import AccessToken

from app._client_api._trueconf_server_ai.client import AiApiError
from app._client_api._trueconf_server_ai.models import AiTokenPair


def _pair(a: str = "ai-a", r: str = "ai-r") -> AiTokenPair:
    return AiTokenPair(access_token=a, refresh_token=r)


@pytest.fixture
def _access_token():
    at = AccessToken(token="tc-access-test", client_id="user-1", scopes=[])
    with patch("app.mcp.auth.trueconf_server_ai.get_access_token", return_value=at):
        yield at


@pytest.fixture
def _sai_resolved(mock_config_set):
    import asyncio

    from app.mcp import close_http_client, init_http_client
    from app.mcp.auth import trueconf_server_ai as ai_auth

    mock_config_set.ai_server_url = "https://sai.example"
    init_http_client()
    yield
    ai_auth.reset_ai_auth_cache()
    asyncio.run(close_http_client())


def _key(tc_token: str) -> str:
    return hashlib.sha256(tc_token.encode()).hexdigest()


@pytest.mark.usefixtures("_access_token")
async def test_sai_base_uses_configured_url(mock_config_set):
    """--ai-server-url из конфига используется напрямую, без запроса к TCS."""
    from app.mcp.auth import trueconf_server_ai as ai_auth

    mock_config_set.ai_server_url = "https://sai.example"
    ai_auth.reset_ai_auth_cache()
    sai_base, err = await ai_auth.resolve_sai_base()
    assert sai_base == "https://sai.example"
    assert err is None


@pytest.mark.usefixtures("_access_token")
async def test_sai_base_bare_host_defaults_to_https(mock_config_set):
    """Голый хост без схемы → https:// по умолчанию."""
    from app.mcp.auth import trueconf_server_ai as ai_auth

    mock_config_set.ai_server_url = "sai01t.trueconf.name"
    sai_base, err = await ai_auth.resolve_sai_base()
    assert err is None
    assert sai_base == "https://sai01t.trueconf.name"


@pytest.mark.usefixtures("_access_token")
async def test_sai_base_http_scheme_is_kept(mock_config_set):
    """Явная http:// схема сохраняется (plain HTTP AI Server)."""
    from app.mcp.auth import trueconf_server_ai as ai_auth

    mock_config_set.ai_server_url = "http://10.110.2.39"
    sai_base, err = await ai_auth.resolve_sai_base()
    assert err is None
    assert sai_base == "http://10.110.2.39"


@pytest.mark.usefixtures("_access_token")
async def test_sai_base_not_configured_returns_error(mock_config_set):
    """Без ai_server_url → понятный error-dict, а не запрос /servers-ai."""
    from app.mcp.auth import trueconf_server_ai as ai_auth

    ai_auth.reset_ai_auth_cache()
    sai_base, err = await ai_auth.resolve_sai_base()
    assert sai_base is None
    assert err is not None
    assert err["error"] == "ai_server_not_configured"


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_get_pair_exchanges_and_caches(mock_config_set):
    from app.mcp.auth import trueconf_server_ai as ai_auth

    pair = _pair()
    with patch("app._client_api._trueconf_server_ai.client.auth_from_tcs", AsyncMock(return_value=pair)) as ex:
        got, err = await ai_auth.get_ai_token_pair("tc-access-test")
    assert err is None
    assert got is pair
    ex.assert_awaited_once()
    # второй вызов — из кэша, без нового exchange
    with patch("app._client_api._trueconf_server_ai.client.auth_from_tcs", AsyncMock()) as ex2:
        got2, err2 = await ai_auth.get_ai_token_pair("tc-access-test")
    assert got2 is pair
    assert err2 is None
    ex2.assert_not_awaited()


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_get_pair_domain_fallback(mock_config_set):
    from app._client_api._trueconf_server_ai.client import AiApiError
    from app.mcp.auth import trueconf_server_ai as ai_auth

    calls = []

    async def fake_exchange(client, sai_base, domain, token):
        calls.append(domain)
        if domain == "https://server.example":
            return _pair()
        raise AiApiError(500, "provider (full) with host X not found")

    with patch("app._client_api._trueconf_server_ai.client.auth_from_tcs", side_effect=fake_exchange):
        got, err = await ai_auth.get_ai_token_pair("tc-access-test")
    assert err is None
    assert got is not None
    assert calls == ["server.example", "https://server.example"]


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_get_pair_tcs_route_not_found_maps_to_wrong_host(mock_config_set):
    """404 routeNotFound (TrueConf Server envelope) → диагностика, а не generic ai_exchange_failed.

    Это сценарий URL-хайджека: запрос ушёл в TrueConf Server (`/api/v4/...`),
    который отвечает именно таким форматом ошибки — без trace_id/routeNotFound
    здесь не обойтись, это единственный надёжный признак «не тот хост».
    """
    from app._client_api._trueconf_server_ai.client import AiApiError
    from app.mcp.auth import trueconf_server_ai as ai_auth

    tcs_404 = {
        "error": {
            "code": 404,
            "message": "Not Found",
            "trace_id": "8627832443",
            "errors": [{"reason": "routeNotFound"}],
        }
    }
    with patch(
        "app._client_api._trueconf_server_ai.client.auth_from_tcs",
        AsyncMock(side_effect=AiApiError(404, str(tcs_404))),
    ):
        pair, err = await ai_auth.get_ai_token_pair("tc-access-test")
    assert pair is None
    assert err is not None
    assert err["error"] == "ai_server_wrong_host"
    assert "TrueConf Server" in err["message"]


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_get_pair_scheme_less_url_maps_to_invalid_url(mock_config_set):
    """ValueError из гварда (URL без схемы) → ai_server_url_invalid, не паника."""
    from app.mcp.auth import trueconf_server_ai as ai_auth

    with patch(
        "app._client_api._trueconf_server_ai.client.auth_from_tcs",
        AsyncMock(side_effect=ValueError("AI Server URL must include a scheme (http:// or https://)")),
    ):
        pair, err = await ai_auth.get_ai_token_pair("tc-access-test")
    assert pair is None
    assert err is not None
    assert err["error"] == "ai_server_url_invalid"


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_ai_request_401_refresh_then_retry(mock_config_set):
    from app.mcp.auth import trueconf_server_ai as ai_auth

    old_pair = _pair("old-a", "old-r")
    new_pair = _pair("new-a", "new-r")
    ai_auth._token_cache[_key("tc-access-test")] = old_pair

    async def fake_raw(client, method, url, **kwargs):
        if kwargs.get("access_token") == "old-a":
            raise AiApiError(401, "Authorization required.")
        return {"transcriptions": []}

    with (
        patch("app.mcp.auth.trueconf_server_ai.ai_client._request", side_effect=fake_raw),
        patch(
            "app.mcp.auth.trueconf_server_ai.ai_client.auth_refresh",
            AsyncMock(return_value=new_pair),
        ),
    ):
        result = await ai_auth.sai_request("GET", "/api/user/v1/transcriptions")
    assert result == {"transcriptions": []}


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_cache_is_per_user(mock_config_set):
    """Токены двух пользователей не смешиваются в кэше."""
    from app.mcp.auth import trueconf_server_ai as ai_auth

    with patch(
        "app._client_api._trueconf_server_ai.client.auth_from_tcs",
        AsyncMock(side_effect=[_pair("a1", "r1"), _pair("a2", "r2")]),
    ):
        p1, e1 = await ai_auth.get_ai_token_pair("token-1")
        p2, e2 = await ai_auth.get_ai_token_pair("token-2")
    assert e1 is None
    assert e2 is None
    assert p1.access_token == "a1"
    assert p2.access_token == "a2"


@pytest.mark.usefixtures("_access_token", "_sai_resolved")
async def test_ai_request_network_error_returns_dict(mock_config_set):
    """AI-сервер недоступен (DNS/таймаут/TLS) → network_error dict, не исключение."""
    import httpx

    from app.mcp.auth import trueconf_server_ai as ai_auth

    ai_auth._token_cache[_key("tc-access-test")] = _pair()
    with patch(
        "app.mcp.auth.trueconf_server_ai.ai_client._request",
        AsyncMock(side_effect=httpx.ConnectError("connection refused")),
    ):
        result = await ai_auth.sai_request("GET", "/api/user/v1/transcriptions")
    assert result["error"] == "network_error"


async def test_ai_request_no_mcp_token_returns_auth_required(mock_config_set):
    from app.mcp.auth import trueconf_server_ai as ai_auth

    ai_auth.reset_ai_auth_cache()
    with patch("app.mcp.auth.trueconf_server_ai.get_access_token", return_value=None):
        result = await ai_auth.sai_request("GET", "/api/user/v1/transcriptions")
    assert result["error"] == "authorization_required"
