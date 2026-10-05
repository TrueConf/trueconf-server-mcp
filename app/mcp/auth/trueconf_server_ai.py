"""AI Server auth glue: from-tcs exchange, in-memory token cache, sai_request.

Flow (verified live on 2026-10-01):
1. The AI Server address comes from configuration: ``--ai-server-url``
   / ``AI_SERVER_URL``. It is NOT discovered via TCS API — GET /servers-ai
   requires admin/serverais rights and returns 403 for regular users.
2. The user's TrueConf token is exchanged on the AI Server:
   POST /api/user/v1/auth/from-tcs {domain, token} → {access_token,
   refresh_token, ...}. ``domain`` is the TCS host as registered in the AI
   Server's provider config — cfg.server first, then https-scheme fallback.
3. Pairs are cached in-memory keyed by sha256(tc_token); access tokens live
   ~24h, refresh ~30d. On AI 401: one refresh, then one re-exchange.
"""

import asyncio
import hashlib
import logging
from typing import Any

import httpx
from fastmcp.server.dependencies import get_access_token

from app._client_api._trueconf_server_ai import client as ai_client
from app._client_api._trueconf_server_ai.models import AiTokenPair
from app.config import get_config
from app.mcp.errors import make_error

logger = logging.getLogger(__name__)

_token_cache: dict[str, AiTokenPair] = {}
_lock = asyncio.Lock()


def reset_ai_auth_cache() -> None:
    """Clear the module-level token cache (test helper)."""
    _token_cache.clear()


async def resolve_sai_base() -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the AI Server base URL from config. Returns (sai_base, error).

    The scheme is optional in the config value: a bare host gets ``https://``
    prepended, an explicit ``http://`` (plain-HTTP AI Server) is kept as-is.
    """
    url = (get_config().ai_server_url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = f"https://{url}"
    if not url:
        return None, make_error(
            "ai_server_not_configured",
            message=(
                "The TrueConf AI Server URL is not configured. Ask your "
                "administrator to start the MCP server with --ai-server-url "
                "(or set the AI_SERVER_URL environment variable), e.g. "
                "sai01t.trueconf.name (https by default) or http://10.110.2.39 "
                "for a plain-HTTP AI Server."
            ),
            how_to={
                "1": "Ask the administrator to set --ai-server-url / AI_SERVER_URL",
                "2": "Retry after the URL is configured",
            },
        )
    return url, None


async def _exchange(client, sai_base: str, tc_token: str) -> AiTokenPair:
    """Exchange the TC token, retrying once with an https-scheme domain."""
    cfg = get_config()
    try:
        return await ai_client.auth_from_tcs(client, sai_base, cfg.server, tc_token)
    except ai_client.AiApiError as e:
        if "not found" not in e.description:
            raise
        logger.info("from-tcs host retry with https scheme: %s", cfg.server)
        return await ai_client.auth_from_tcs(client, sai_base, f"https://{cfg.server}", tc_token)


async def get_ai_token_pair(
    tc_token: str,
) -> tuple[AiTokenPair | None, dict[str, Any] | None]:
    """Return the cached AI token pair for this TC token, exchanging if needed."""
    key = hashlib.sha256(tc_token.encode()).hexdigest()
    async with _lock:
        pair = _token_cache.get(key)
    if pair is not None:
        return pair, None
    from app.mcp import get_http_client

    sai_base, err = await resolve_sai_base()
    if err is not None:
        return None, err
    try:
        pair = await _exchange(get_http_client(), sai_base, tc_token)
    except ai_client.AiApiError as e:
        if e.status_code == 404 and "routeNotFound" in e.description:
            # TrueConf Server API v4 envelope (trace_id + reason: routeNotFound):
            # the request was routed to a TrueConf Server, not the AI Server.
            return None, make_error(
                "ai_server_wrong_host",
                detail=e.description,
                status_code=e.status_code,
                message=(
                    "The AI Server request reached a TrueConf Server instead of "
                    "the AI Server (HTTP 404 routeNotFound). Check that "
                    "AI_SERVER_URL points at the AI Server and includes a scheme, "
                    "e.g. https://sai01t.trueconf.name."
                ),
                how_to={
                    "1": "Verify AI_SERVER_URL / --ai-server-url points at the AI Server, not the TrueConf Server",
                    "2": "Make sure the URL includes http:// or https://",
                    "3": "Retry after fixing the URL",
                },
            )
        return None, make_error(
            "ai_exchange_failed",
            detail=e.description,
            status_code=e.status_code,
            message=("Failed to authorize on the TrueConf AI Server with your TrueConf token."),
        )
    except ValueError as e:
        # Guard in ai_client._request: scheme-less URL would resolve against base_url.
        return None, make_error("ai_server_url_invalid", detail=str(e))
    except httpx.HTTPError as e:
        logger.warning("AI network error during exchange: %s", e)
        return None, make_error("network_error", detail=str(e))
    async with _lock:
        _token_cache[key] = pair
    return pair, None


async def _refresh_pair(
    client: httpx.AsyncClient,
    sai_base: str,
    pair: AiTokenPair,
    tc_token: str,
) -> tuple[AiTokenPair | None, dict[str, Any] | None]:
    """Renew the AI pair after a 401: refresh first, then re-exchange.

    Returns ``(new_pair, None)`` on success (and caches it), or
    ``(None, error_dict)`` when the AI Server authorization cannot be
    renewed (``ai_token_invalid``) or the network is down
    (``network_error``). Never more than one retry.
    """
    try:
        new_pair = await ai_client.auth_refresh(client, sai_base, pair.refresh_token)
    except (ai_client.AiApiError, httpx.HTTPError):
        new_pair = None
    if new_pair is None:
        try:
            new_pair = await _exchange(client, sai_base, tc_token)
        except ai_client.AiApiError as e:
            return None, make_error(
                "ai_token_invalid",
                detail=e.description,
                message="AI Server authorization expired and could not be renewed.",
            )
        except httpx.HTTPError as e:
            return None, make_error("network_error", detail=str(e))
    async with _lock:
        _token_cache[hashlib.sha256(tc_token.encode()).hexdigest()] = new_pair
    return new_pair, None


def _ai_server_error_dict(e: ai_client.AiApiError) -> dict[str, Any]:
    return make_error("ai_server_error", detail=e.description, status_code=e.status_code)


async def _retry_request(
    client: httpx.AsyncClient,
    method: str,
    sai_base: str,
    path: str,
    *,
    pair: AiTokenPair,
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Re-run the request with a renewed pair (after a 401 refresh)."""
    try:
        return await ai_client._request(
            client,
            method,
            f"{sai_base}{path}",
            access_token=pair.access_token,
            params=params,
        )
    except ai_client.AiApiError as e:
        return _ai_server_error_dict(e)
    except ValueError as e:
        return make_error("ai_server_url_invalid", detail=str(e))
    except httpx.HTTPError as e:
        logger.warning("AI network error on retry %s %s: %s", method, path, e)
        return make_error("network_error", detail=str(e))


async def sai_request(method: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Authenticated request against the AI Server on behalf of the user.

    401 handling: one refresh attempt, then one re-exchange, then an
    ``ai_token_invalid`` error dict. Never more than one retry.
    """
    from app.mcp import _auth_required_dict, get_http_client

    token = get_access_token()
    if token is None:
        return _auth_required_dict()

    sai_base, err = await resolve_sai_base()
    if err is not None:
        return err
    pair, err = await get_ai_token_pair(token.token)
    if err is not None:
        return err

    client = get_http_client()

    try:
        return await ai_client._request(
            client,
            method,
            f"{sai_base}{path}",
            access_token=pair.access_token,
            params=params,
        )
    except ai_client.AiApiError as e:
        if e.status_code != 401:
            return _ai_server_error_dict(e)
    except ValueError as e:
        return make_error("ai_server_url_invalid", detail=str(e))
    except httpx.HTTPError as e:
        logger.warning("AI network error %s %s: %s", method, path, e)
        return make_error("network_error", detail=str(e))

    # 401: refresh → retry; re-exchange → retry; give up.
    new_pair, err = await _refresh_pair(client, sai_base, pair, token.token)
    if err is not None:
        return err
    return await _retry_request(client, method, sai_base, path, pair=new_pair, params=params)
