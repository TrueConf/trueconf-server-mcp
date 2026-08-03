"""HTTP UI routes registered on the FastMCP server instance.

Importing this module is a side-effect registration: the 8 unconditional
routes (`/`, `/success`, `/error`, `/api/health`, `/static/app.css`,
`/static/app.js`, `/favicon.ico`, `/logo.png`) are registered on `mcp` at
import time. The conditional `/auth/callback` route (token auth mode only)
is registered separately via `register_login_callback()` — call it from
`run_server()` when `auth_mode != "oauth"`.

OAuth login flow:
    `/` (login form) → TrueConf Server `auth2/auth` → `/auth/callback`
    → exchange code for TrueConf tokens → create our long-lived token
    via `get_token_store()` → redirect to `/success?token=...` →
    `/success` renders the token + MCP client configs. Errors redirect to
    `/error`.
"""

import hashlib
import asyncio
import logging
import time
import weakref
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.config import get_config
from app.mcp import get_token_store, mcp
from app.mcp.i18n import detect_lang, is_explicit_choice, set_lang_cookie
from app.mcp.pages import (
    error_page as render_error_page,
    login_page as render_login_page,
    success_page as render_success_page,
)

logger = logging.getLogger(__name__)

# app/mcp/routes.py → app/mcp → app/ → app/web
_WEB_DIR = Path(__file__).parent.parent / "web"

# OAuth authorization codes are single-use. Some TrueConf Server web flows
# deliver the same callback URL more than once, so remember a completed code
# briefly and return the already-issued MCP token instead of exchanging it
# again. Store only a hash of the OAuth code.
_COMPLETED_CALLBACKS: dict[str, tuple[str, float]] = {}
_CALLBACK_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)
_COMPLETED_CALLBACK_TTL_SECONDS = 60
_HEALTH_CACHE: tuple[bool, float] | None = None
_HEALTH_SUCCESS_TTL_SECONDS = 15
_HEALTH_FAILURE_TTL_SECONDS = 3


def _callback_code_key(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _get_completed_callback(code: str) -> str | None:
    now = time.monotonic()
    key = _callback_code_key(code)
    for expired_key, (_, expires_at) in list(_COMPLETED_CALLBACKS.items()):
        if expires_at <= now:
            _COMPLETED_CALLBACKS.pop(expired_key, None)
    entry = _COMPLETED_CALLBACKS.get(key)
    if entry is None or entry[1] <= now:
        return None
    return entry[0]


def _remember_completed_callback(code: str, token: str) -> None:
    _COMPLETED_CALLBACKS[_callback_code_key(code)] = (
        token,
        time.monotonic() + _COMPLETED_CALLBACK_TTL_SECONDS,
    )


def _set_mcp_token_cookie(response: Response, token: str, no_tls: bool) -> None:
    response.set_cookie(
        "mcp_token",
        token,
        max_age=60,
        httponly=True,
        secure=not no_tls,
        samesite="none",
        path="/",
    )
    # Keep the navigation intent separate from the token. The token remains
    # available on /success for a language reload; this marker is one-shot.
    response.set_cookie(
        "mcp_login_pending",
        "1",
        max_age=60,
        httponly=True,
        secure=not no_tls,
        samesite="none",
        path="/",
    )


async def _trueconf_is_healthy() -> bool:
    """Check TrueConf availability with a small cache to avoid polling load."""
    global _HEALTH_CACHE

    now = time.monotonic()
    if _HEALTH_CACHE is not None and _HEALTH_CACHE[1] > now:
        return _HEALTH_CACHE[0]

    try:
        from app.mcp import get_http_client

        await get_http_client().get("server", timeout=3.0)
        healthy = True
    except httpx.HTTPError:
        healthy = False
    ttl = _HEALTH_SUCCESS_TTL_SECONDS if healthy else _HEALTH_FAILURE_TTL_SECONDS
    _HEALTH_CACHE = (healthy, now + ttl)
    return healthy


def _cors(response: Response, request: Request | None = None) -> Response:
    """Add CORS headers for cross-origin requests from TrueConf Server.

    TrueConf Server's /oauth2/authorize flow uses fetch() with credentials,
    so /auth/callback is a credentialed cross-site request. For such
    requests the browser requires the specific Origin to be echoed (not
    ``*``) and ``Access-Control-Allow-Credentials: true`` — otherwise the
    response is blocked and Set-Cookie is dropped, causing a login loop.
    """
    origin = request.headers.get("origin") if request else None
    cfg = get_config()
    allowed_origins = {
        f"{parsed.scheme}://{parsed.netloc}"
        for value in (cfg.trueconf_base, cfg.mcp_base_url)
        if (parsed := urlsplit(value)).scheme and parsed.netloc
    }
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    elif not origin:
        response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    return response


@mcp.custom_route("/favicon.ico", methods=["GET", "OPTIONS"])
async def favicon(request: Request) -> Response:
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204))
    content = (_WEB_DIR / "assets" / "favicon.ico").read_bytes()
    return Response(content, media_type="image/x-icon")


@mcp.custom_route("/logo.png", methods=["GET", "OPTIONS"])
async def logo(request: Request) -> Response:
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204))
    content = (_WEB_DIR / "assets" / "logo.png").read_bytes()
    return Response(content, media_type="image/png")


@mcp.custom_route("/static/app.css", methods=["GET", "OPTIONS"])
async def serve_app_css(request: Request) -> Response:
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204))
    content = (_WEB_DIR / "static" / "app.css").read_text(encoding="utf-8")
    return Response(content, media_type="text/css")


@mcp.custom_route("/static/app.js", methods=["GET", "OPTIONS"])
async def serve_app_js(request: Request) -> Response:
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204))
    content = (_WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    return Response(content, media_type="application/javascript")


@mcp.custom_route("/api/health", methods=["GET", "OPTIONS"])
async def health_check(request: Request) -> Response:
    """Proxy health check for TrueConf Server.

    Browser cannot reach TrueConf Server directly (self-signed cert),
    so this endpoint makes a server-side request and returns JSON.
    """
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204))

    if await _trueconf_is_healthy():
        return _cors(
            Response(
                '{"status": "ok"}',
                media_type="application/json",
            )
        )
    resp = Response(
        '{"status": "error"}',
        media_type="application/json",
        status_code=503,
    )
    return _cors(resp)


@mcp.custom_route("/", methods=["GET", "OPTIONS"])
async def login_page(request: Request) -> Response:
    """Show the login form (start of the OAuth flow).

    If the one-shot ``mcp_login_pending`` cookie is present, redirect to
    /success instead of showing the login form. This handles the
    TrueConf Server OAuth flow where the callback is delivered via fetch()
    from JS — after the fetch, TrueConf's JS navigates the browser to the
    base URL (e.g. ``/&state=null``), not to /success. Without this check,
    the user would see the login page instead of the token page.
    """
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204), request)

    cfg = get_config()
    if request.cookies.get("mcp_login_pending"):
        response = RedirectResponse(f"{cfg.mcp_base_url}/success", status_code=302)
        response.delete_cookie("mcp_login_pending", path="/")
        return _cors(response, request)

    query_params = dict(request.query_params)
    lang = detect_lang(request)

    auth_url = f"{cfg.trueconf_base}/oauth2/authorize?{
        urlencode(
            {
                'client_id': cfg.client_id,
                'response_type': 'code',
                'redirect_uri': cfg.login_callback_url,
            }
        )
    }"
    response = render_login_page(auth_url, lang, query_params, cfg.trueconf_base)

    if is_explicit_choice(request):
        set_lang_cookie(response, lang)
    return _cors(response, request)


@mcp.custom_route("/&state=null", methods=["GET", "OPTIONS"])
async def malformed_state_redirect(request: Request) -> Response:
    """Recover from TrueConf's malformed final navigation to ``/&state=null``."""
    cfg = get_config()
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204), request)
    return _cors(RedirectResponse(f"{cfg.mcp_base_url}/", status_code=302), request)


@mcp.custom_route("/success", methods=["GET", "OPTIONS"])
async def success_page(request: Request) -> Response:
    """Show the token page after a successful OAuth callback.

    Reads our UUID token from the ``mcp_token`` httpOnly cookie (set by
    ``/auth/callback``). If the cookie is missing, redirects to ``/`` for a
    re-login. The cookie is short-lived (60 seconds) so the page can be
    re-rendered when the visitor changes language.
    """
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204), request)

    cfg = get_config()
    token = request.cookies.get("mcp_token")
    if not token:
        return _cors(RedirectResponse(f"{cfg.mcp_base_url}/", status_code=302), request)

    # Read display info from the token store (less leakage than query params).
    name = ""
    user_id = ""
    token_store = get_token_store()
    if token_store is not None:
        record = await token_store.get_by_token(token)
        if record:
            name = record.display_name
            user_id = record.user_id

    query_params = dict(request.query_params)
    lang = detect_lang(request)

    response = render_success_page(
        token,
        name,
        user_id,
        cfg.api_token_ttl,
        cfg.mcp_base_url,
        lang,
        query_params,
        cfg.trueconf_base,
    )
    # Direct callback navigation can bypass /. Consume the marker here too,
    # so a later visit to / renders login instead of returning to /success.
    if request.cookies.get("mcp_login_pending"):
        response.delete_cookie("mcp_login_pending", path="/")
    if is_explicit_choice(request):
        set_lang_cookie(response, lang)
    return _cors(response, request)


@mcp.custom_route("/error", methods=["GET", "OPTIONS"])
async def error_page(request: Request) -> Response:
    """Show the OAuth error page."""
    if request.method == "OPTIONS":
        return _cors(HTMLResponse("", status_code=204), request)

    cfg = get_config()
    query_params = dict(request.query_params)
    lang = detect_lang(request)

    response = render_error_page(query_params, lang, cfg.trueconf_base)

    if is_explicit_choice(request):
        set_lang_cookie(response, lang)
    return _cors(response, request)


# ── /auth/callback helpers (testable, no mcp.custom_route needed) ─────────


def _map_exception_to_code(exc: Exception) -> str:
    """Map a login-callback exception to a stable error code (T9).

    The raw ``str(e)`` is logged server-side but never sent to the client.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        return "network_error"
    if isinstance(exc, KeyError):
        return "token_exchange_failed"
    return "create_token_failed"


async def _handle_login_callback(request: Request) -> Response:
    """Core logic for /auth/callback — extracted for testability.

    Exchanges the OAuth code for TrueConf tokens, creates our long-lived API
    token, sets it in an httpOnly cookie, and redirects to ``/success``.
    Errors redirect to ``/error?code=...`` with a stable code (not raw str(e)).
    """
    cfg = get_config()
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        params = urlencode({"code": error})
        return _cors(
            RedirectResponse(f"{cfg.mcp_base_url}/error?{params}", status_code=302),
            request,
        )

    if not code:
        # No code and no error — user hit /auth/callback directly. Send them
        # back to the login page instead of a blank 200.
        return _cors(RedirectResponse(f"{cfg.mcp_base_url}/", status_code=302), request)

    code_key = _callback_code_key(code)
    callback_lock = _CALLBACK_LOCKS.setdefault(code_key, asyncio.Lock())

    async with callback_lock:
        completed_token = _get_completed_callback(code)
        if completed_token:
            logger.info("Ignoring duplicate OAuth callback for an already exchanged code")
            response = RedirectResponse(f"{cfg.mcp_base_url}/success", status_code=302)
            _set_mcp_token_cookie(response, completed_token, cfg.no_tls)
            return _cors(response, request)

        return await _exchange_login_code(request, code)


async def _exchange_login_code(request: Request, code: str) -> Response:
    """Exchange one OAuth code. Caller serializes calls for the same code."""
    cfg = get_config()
    try:
        logger.info("Received OAuth code, exchanging for TrueConf token")
        from app.mcp import get_http_client

        token_data = {
            "grant_type": "authorization_code",
            "auth_code": code,
            "client_id": cfg.client_id,
            "client_secret": cfg.secret,
            "redirect_uri": cfg.login_callback_url,
        }
        http_client = get_http_client()
        resp = await http_client.post("oauth2/token", json=token_data)

        if resp.is_error:
            logger.warning("Token exchange failed: %s", resp.status_code)
            params = urlencode(
                {"code": "token_exchange_failed", "detail": resp.status_code}
            )
            return _cors(
                RedirectResponse(f"{cfg.mcp_base_url}/error?{params}", status_code=302),
                request,
            )

        data = resp.json()
        trueconf_access_token = data["access_token"]
        trueconf_refresh_token = data.get("refresh_token")
        trueconf_expires_in = int(data.get("expires_in", 3600))
        display_name = data.get("display_name", "")
        user_id = data.get("user_id", "")

        # The token response does not always include the user's current
        # display name. Fetch the canonical profile value for the success
        # page, while keeping login available if the optional lookup fails.
        try:
            me_response = await http_client.get(
                "/me",
                headers={"Authorization": f"Bearer {trueconf_access_token}"},
                timeout=2.0,
            )
            if not me_response.is_error:
                me_data = me_response.json()
                me_user = me_data.get("user", {})
                me_display_name = (
                    me_user.get("display_name") if isinstance(me_user, dict) else None
                )
                if isinstance(me_display_name, str) and me_display_name:
                    display_name = me_display_name
            else:
                logger.warning("TrueConf /me lookup failed: %s", me_response.status_code)
        except (httpx.HTTPError, ValueError):
            logger.warning("TrueConf /me lookup failed", exc_info=True)

        logger.info(
            "TrueConf token received for user=%s (user_id=%s, has_refresh=%s)",
            display_name,
            user_id,
            bool(trueconf_refresh_token),
        )

        # Create our own long-lived token
        token_store = get_token_store()
        if token_store is None:
            raise RuntimeError("Token store not initialized")
        api_token = await token_store.create_token(
            user_id=user_id,
            display_name=display_name,
            trueconf_access_token=trueconf_access_token,
            trueconf_refresh_token=trueconf_refresh_token,
            trueconf_expires_in=trueconf_expires_in,
        )

        # TrueConf Server delivers this callback through fetch(). Returning a
        # redirect here would make fetch() follow /success and then the
        # TrueConf UI would still navigate to /?state=null. Keep the fetch at
        # this endpoint; the short HTML redirect is used only for a direct
        # browser navigation. A repeated callback is handled from the cache
        # above and receives a normal redirect to /success.
        _remember_completed_callback(code, api_token.token)
        response = HTMLResponse(
            "<!DOCTYPE html><html><head>"
            '<meta http-equiv="refresh" content="0;url=/success">'
            "<title>Redirecting…</title></head><body></body></html>",
            status_code=200,
        )
        _set_mcp_token_cookie(response, api_token.token, cfg.no_tls)
        return _cors(response, request)

    except Exception as e:
        logger.exception("Login callback error")
        params = urlencode({"code": _map_exception_to_code(e)})
        return _cors(
            RedirectResponse(f"{cfg.mcp_base_url}/error?{params}", status_code=302),
            request,
        )


def register_login_callback() -> None:
    """Register /auth/callback route (token auth mode only).

    Defined as a function so it runs after Config is set (needs auth_mode).
    The handler exchanges the OAuth code for TrueConf tokens, creates our
    long-lived API token via ``get_token_store()``, sets it in an httpOnly
    ``mcp_token`` cookie, and redirects to ``/success`` (no token in the URL).
    Errors redirect to ``/error?code=...`` with a stable code.
    """

    @mcp.custom_route("/auth/callback", methods=["GET", "OPTIONS"])
    async def login_callback(request: Request) -> Response:
        if request.method == "OPTIONS":
            return _cors(HTMLResponse("", status_code=204), request)
        return await _handle_login_callback(request)
