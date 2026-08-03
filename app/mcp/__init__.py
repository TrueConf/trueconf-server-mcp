import base64
import logging
import httpx
from typing import Any
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.types import File

from app.config import get_config
from app.mcp.errors import make_error

logger = logging.getLogger(__name__)

from app.mcp.logging_utils import mask_token as mask_token  # noqa: E402, F401


# ── Shared httpx client (created in run_server, closed on shutdown) ──────
_http_client: httpx.AsyncClient | None = None


def init_http_client() -> None:
    """Create the shared httpx AsyncClient from the current Config."""
    global _http_client
    cfg = get_config()
    _http_client = httpx.AsyncClient(
        base_url=f"https://{cfg.server}/api/v4",
        verify=cfg.verify_ssl,
        timeout=cfg.http_timeout,
    )


async def close_http_client() -> None:
    """Close the shared httpx client (call on shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx client, or raise if not initialized."""
    if _http_client is None:
        raise RuntimeError(
            "HTTP client not initialized — call init_http_client() first"
        )
    return _http_client


# ── MCP Server Instance ─────────────────────────────────────────────────
# `mcp.instructions` is set in main.py after the discovery mode is selected
# (see app/mcp/instructions.py for the per-mode texts).
mcp = FastMCP("TrueConf Server MCP")

# ── Token store (set by run_server after initialization) ─────────────────
_token_store = None


def set_token_store(store) -> None:
    global _token_store
    _token_store = store


def get_token_store():
    """Return the initialized TokenStore, or None if not yet set."""
    return _token_store


def _handle_error(response) -> dict[str, Any]:
    """Parse TrueConf API error response.

    Non-JSON responses (e.g. an HTML 5xx error page from an upstream proxy)
    include the first 500 chars of the body as ``detail`` so production
    incidents are debuggable instead of collapsing to a bare ``HTTP <status>``.
    """
    try:
        data = response.json()
        if "error" in data:
            return make_error(
                str(data["error"]),
                message=str(data.get("message", data["error"])),
            )
        return make_error("upstream_error", message=str(data))
    except Exception:
        body = response.text or ""
        return make_error(
            f"HTTP {response.status_code}",
            detail=body[:500],
        )


def _login_url() -> str:
    """Build the login URL from the current config."""
    return f"{get_config().mcp_base_url.rstrip('/')}/"


def _auth_required_dict() -> dict[str, Any]:
    login_url = _login_url()
    return make_error(
        "authorization_required",
        login_url=login_url,
        message=(
            "Authorization required. Open the login_url in a browser, "
            "log in via TrueConf Server, copy the token, then send it as "
            "an Authorization: Bearer <token> header and reconnect."
        ),
        how_to={
            "1": f"Open {login_url} in a browser",
            "2": "Authorize via TrueConf Server",
            "3": "Copy the token from the page",
            "4": "Add header: Authorization: Bearer <your_token>",
        },
    )


def _token_invalid_dict() -> dict[str, Any]:
    login_url = _login_url()
    return make_error(
        "token_invalid",
        login_url=login_url,
        message="TrueConf token revoked. Re-authorize at login_url.",
        how_to={
            "1": f"Open {login_url} in a browser",
            "2": "Authorize via TrueConf Server",
            "3": "Copy the token from the page",
            "4": "Add header: Authorization: Bearer <your_token>",
        },
    )


async def _call_trueconf(
    method: str, path: str, trueconf_token: str, **kwargs
) -> httpx.Response:
    """Make a single HTTP request to the TrueConf API with the given token."""
    if _http_client is None:
        raise RuntimeError(
            "HTTP client not initialized — call init_http_client() first"
        )
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {trueconf_token}"
    logger.info("REQUEST %s %s", method, path)
    logger.debug(
        "REQUEST %s %s | params=%s | body=%s",
        method,
        path,
        kwargs.get("params"),
        kwargs.get("json"),
    )
    response = await _http_client.request(method, path, headers=headers, **kwargs)
    logger.info(
        "RESPONSE %s %s | status=%d | content-type=%s",
        method,
        path,
        response.status_code,
        response.headers.get("content-type"),
    )
    logger.debug("RESPONSE body %s %s: %s", method, path, response.text[:500])
    return response


async def _try_refresh_trueconf_token(trueconf_token: str) -> str | None:
    """Try to refresh the TrueConf token via the auth provider (T4 per-token lock).

    Returns the fresh TrueConf access token, or None if refresh failed /
    no token-mode auth provider is configured.
    """
    from app.mcp.auth import ApiTokenAuth

    auth = mcp.auth
    if isinstance(auth, ApiTokenAuth):
        return await auth.refresh_by_access_token(trueconf_token)
    return None


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 204:
        return {"status": "success"}
    if response.is_error:
        return _handle_error(response)
    try:
        data = response.json()
    except Exception:
        content_type = response.headers.get("content-type", "")
        if "text/" in content_type:
            return {"content": response.text}
        # Binary content that reached _parse_response — binary endpoints
        # should use _request_file instead (returns an MCP File content
        # block with size guard). This base64 fallback is kept for any
        # hypothetical _request call that encounters binary data.
        return {
            "content_type": content_type,
            "size": len(response.content),
            "data_base64": base64.b64encode(response.content).decode("ascii"),
        }
    if data is None:
        return {}
    if isinstance(data, list):
        return {"data": data}
    return data


async def _request(method: str, path: str, **kwargs) -> dict[str, Any]:
    """Make an authenticated request to TrueConf API.

    Resilience (T5):
    - httpx errors (ConnectError, TimeoutException) → ``network_error`` dict.
    - Upstream 401 → refresh via ``ApiTokenAuth`` (T4 per-token lock) and
      retry once; if refresh fails or the retry is still 401 → ``token_invalid``
      dict so the LLM can tell the user to re-authorize.
    """
    token = get_access_token()
    if token is None:
        return _auth_required_dict()

    try:
        response = await _call_trueconf(method, path, token.token, **kwargs)
    except httpx.HTTPError as e:
        logger.warning("Network error %s %s: %s", method, path, e)
        return make_error("network_error", detail=str(e))

    if response.status_code == 401:
        try:
            new_token = await _try_refresh_trueconf_token(token.token)
        except Exception:
            logger.exception("Token refresh failed unexpectedly")
            return _token_invalid_dict()
        if new_token is None:
            return _token_invalid_dict()
        try:
            response = await _call_trueconf(method, path, new_token, **kwargs)
        except httpx.HTTPError as e:
            logger.warning("Network error on retry %s %s: %s", method, path, e)
            return make_error("network_error", detail=str(e))
        if response.status_code == 401:
            return _token_invalid_dict()

    return _parse_response(response)


async def _request_file(
    method: str,
    path: str,
    *,
    format: str,
    name: str | None = None,
    max_size: int = 10_000_000,
    **kwargs,
) -> File | dict[str, Any]:
    """Make an authenticated request and return a binary response as an MCP
    ``File`` content block.

    Like ``_request`` but for binary endpoints (ICS, CSV exports) — instead
    of base64-encoding the body into a dict (which LLMs cannot use and which
    risks memory bombs), returns a proper ``fastmcp.utilities.types.File``.

    Resilience (same as ``_request``):
    - No token → ``authorization_required`` dict.
    - httpx errors → ``network_error`` dict.
    - Upstream 401 → refresh + retry once → ``token_invalid`` if still 401.

    Size guard: if ``len(response.content) > max_size`` (default 10MB), returns
    a ``file_too_large`` error dict instead of loading the body into the MCP
    message — the LLM gets a hint to use ``download_url`` alternatives.
    """
    token = get_access_token()
    if token is None:
        return _auth_required_dict()

    try:
        response = await _call_trueconf(method, path, token.token, **kwargs)
    except httpx.HTTPError as e:
        logger.warning("Network error %s %s: %s", method, path, e)
        return make_error("network_error", detail=str(e))

    if response.status_code == 401:
        try:
            new_token = await _try_refresh_trueconf_token(token.token)
        except Exception:
            logger.exception("Token refresh failed unexpectedly")
            return _token_invalid_dict()
        if new_token is None:
            return _token_invalid_dict()
        try:
            response = await _call_trueconf(method, path, new_token, **kwargs)
        except httpx.HTTPError as e:
            logger.warning("Network error on retry %s %s: %s", method, path, e)
            return make_error("network_error", detail=str(e))
        if response.status_code == 401:
            return _token_invalid_dict()

    if response.is_error:
        return _handle_error(response)

    size = len(response.content)
    if size > max_size:
        logger.warning(
            "Binary response too large %s %s: %d bytes > %d limit",
            method,
            path,
            size,
            max_size,
        )
        return make_error(
            "file_too_large",
            detail=f"{size} bytes > {max_size} limit",
            message=(
                "The file is too large to return via MCP. Use the download_url "
                "from get_recording / list_recordings instead."
            ),
        )

    return File(data=response.content, format=format, name=name)
