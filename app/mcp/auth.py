from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Any, cast

from fastmcp.server.auth import AccessToken, AuthProvider

from app.config import Config
from app.mcp.token_store import TokenStore

logger = logging.getLogger(__name__)


def _patch_auth_middleware_optional() -> None:
    """Make RequireAuthMiddleware pass through unauthenticated requests.

    When no Bearer token is present, the request flows through to the MCP handler.
    Tools check get_access_token() themselves and return user-friendly errors.

    .. warning::
       Monkeypatches ``fastmcp.server.auth.middleware.RequireAuthMiddleware.__call__``
       on the library class — a fastmcp upgrade can break this. The project pins
       ``fastmcp==3.4.2`` to protect the patch. Alternative: fork fastmcp or use a
       middleware wrapper.
    """
    import fastmcp.server.auth.middleware as mw
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

    async def _optional_call(self, scope, receive, send) -> None:
        auth_user = scope.get("user")
        if isinstance(auth_user, AuthenticatedUser):
            auth_credentials = scope.get("auth")
            for required_scope in self.required_scopes:
                if (
                    auth_credentials is None
                    or required_scope not in auth_credentials.scopes
                ):
                    await self._send_auth_error(
                        send,
                        403,
                        "insufficient_scope",
                        f"Required scope: {required_scope}",
                    )
                    return
            await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    mw.RequireAuthMiddleware.__call__ = cast(Any, _optional_call)


class ApiTokenAuth(AuthProvider):
    """Custom auth provider that validates our own long-lived API tokens.

    Flow:
    1. Client sends our token in Authorization header
    2. We look up the TrueConf credentials in TokenStore
    3. If TrueConf access token is expired, refresh it via /api/v4/oauth2/token
    4. Return AccessToken with the (fresh) TrueConf access token
    """

    def __init__(
        self,
        token_store: TokenStore,
        server: str,
        client_id: str,
        client_secret: str,
        verify_ssl: bool = True,
        login_url: str = "/",
    ) -> None:
        super().__init__()
        self.token_store = token_store
        self.server = server
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_ssl = verify_ssl
        self._login_url = login_url
        # Per-token locks prevent thundering herd on concurrent refresh.
        # Weak values keep a lock alive exactly while callers use/wait on it.
        # Removing a lock explicitly is unsafe: a late waiter may still hold
        # the old object while a new caller creates a second lock for the token.
        self._refresh_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        # Allow unauthenticated requests through — tools handle auth themselves
        _patch_auth_middleware_optional()

    async def verify_token(self, token: str) -> AccessToken | None:
        record = await self.token_store.get_by_token(token)
        if not record:
            return None

        # Our own token has expired (api_token_ttl elapsed) — reject outright.
        if record.expires_at <= time.time():
            logger.warning("Our API token expired for user=%s", record.user_id)
            return None

        # If TrueConf token is expired — refresh it under a per-token lock so
        # concurrent requests share one refresh (no thundering herd).
        if record.trueconf_expires_at <= time.time():
            if not record.trueconf_refresh_token:
                logger.warning(
                    "TrueConf token expired for user=%s and no refresh_token available",
                    record.user_id,
                )
                return None

            lock = self._refresh_locks.setdefault(token, asyncio.Lock())
            async with lock:
                # Re-check after acquiring the lock: another request may
                # have already refreshed the token while we were waiting.
                record = await self.token_store.get_by_token(token)
                if not record:
                    return None
                if record.trueconf_expires_at > time.time():
                    return AccessToken(
                        token=record.trueconf_access_token,
                        client_id=record.user_id,
                        scopes=[],
                    )
                if not record.trueconf_refresh_token:
                    await self.token_store.delete(token)
                    return None

                refreshed = await self._refresh_trueconf_token(
                    record.trueconf_refresh_token
                )
                if not refreshed:
                    logger.warning(
                        "TrueConf token refresh failed for user=%s — "
                        "removing dead token",
                        record.user_id,
                    )
                    await self.token_store.delete(token)
                    return None

                await self.token_store.update_trueconf_tokens(
                    token,
                    refreshed["access_token"],
                    refreshed.get("refresh_token"),
                    time.time() + int(refreshed.get("expires_in", 3600)),
                )
                record = await self.token_store.get_by_token(token)
                if not record:
                    return None
                logger.info("Refreshed TrueConf token for user=%s", record.user_id)
        return AccessToken(
            token=record.trueconf_access_token,
            client_id=record.user_id,
            scopes=[],
        )

    async def refresh_by_access_token(self, trueconf_token: str) -> str | None:
        """Refresh the TrueConf token for a record matching this access token.

        Uses the O(1) secondary index (trueconf_access_token -> our token key)
        instead of scanning all tokens.
        """
        our_token = await self.token_store.get_by_tc_access_token(trueconf_token)
        if our_token is None:
            return None
        at = await self.verify_token(our_token)
        return at.token if at else None

    async def _refresh_trueconf_token(self, refresh_token: str) -> dict | None:
        """POST /api/v4/oauth2/token with grant_type=refresh_token."""
        try:
            from app.mcp import get_http_client

            resp = await get_http_client().post(
                "oauth2/token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            if resp.is_error:
                logger.warning("TrueConf token refresh failed: %s", resp.text)
                return None
            return resp.json()
        except Exception as e:
            logger.exception("TrueConf token refresh error: %s", e)
            return None


def create_auth(
    token_store: TokenStore,
    server: str,
    client_id: str,
    client_secret: str,
    verify_ssl: bool = True,
    login_url: str = "/",
) -> ApiTokenAuth:
    """Create ApiTokenAuth provider (AUTH_MODE=token)."""
    return ApiTokenAuth(
        token_store=token_store,
        server=server,
        client_id=client_id,
        client_secret=client_secret,
        verify_ssl=verify_ssl,
        login_url=login_url,
    )


def create_oauth_auth(
    server: str,
    client_id: str,
    client_secret: str,
    mcp_base_url: str,
    verify_ssl: bool = True,
):
    """Create OAuthProxy provider (AUTH_MODE=oauth) with DCR support.

    .. warning::
       **DISABLED.** This code is dead — ``init_auth`` never calls it. The
       ``_TrueConfTokenVerifier`` below accepted ANY string as a valid token,
       which was an auth bypass. Re-enable only after implementing real
       opaque-token validation against TrueConf Server (e.g. an introspection
       endpoint or a ``/api/v4/me`` lookup).
    """
    from fastmcp.server.auth.oauth_proxy import OAuthProxy
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    # OAuthProxy needs a token_verifier for upstream tokens.
    # TrueConf access tokens are opaque (not JWT), so we create a verifier
    # that always accepts — OAuthProxy handles refresh internally.
    class _TrueConfTokenVerifier(JWTVerifier):
        async def verify_token(self, token: str) -> AccessToken | None:
            return AccessToken(token=token, client_id="", scopes=[])

    token_verifier = _TrueConfTokenVerifier(
        public_key="not-used",
        algorithm="HS256",
    )

    auth = OAuthProxy(
        upstream_authorization_endpoint=f"https://{server}/oauth2/authorize",
        upstream_token_endpoint=f"https://{server}/oauth2/token",
        upstream_client_id=client_id,
        upstream_client_secret=client_secret,
        token_verifier=token_verifier,
        base_url=mcp_base_url,
        redirect_path="/auth/callback",
        require_authorization_consent="remember",
        enable_cimd=False,
    )
    logger.info(
        "OAuthProxy configured: upstream=https://%s, redirect=/auth/callback", server
    )
    return auth


def init_auth(config: Config, token_store: TokenStore):
    """Initialize the auth provider.

    Always returns ``ApiTokenAuth`` (token mode). The OAuth path
    (``create_oauth_auth`` / ``OAuthProxy`` / ``_TrueConfTokenVerifier``) is
    **disabled** — the verifier accepted any string as a valid token, which
    was an auth bypass. The code is kept as dead code for a future re-enable
    after implementing real opaque-token validation against TrueConf Server.

    ``config.auth_mode`` is intentionally ignored.
    """
    return create_auth(
        token_store=token_store,
        server=config.server,
        client_id=config.client_id,
        client_secret=config.secret,
        verify_ssl=config.verify_ssl,
        login_url=f"{config.mcp_base_url}/",
    )
