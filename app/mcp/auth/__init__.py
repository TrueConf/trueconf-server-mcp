"""MCP-layer auth/access glue to the upstream TrueConf services.

- ``trueconf_server``: token auth against TrueConf Server — ``ApiTokenAuth``
  (our UUID token → TrueConf token mapping + auto-refresh), ``init_auth``,
  the (disabled) OAuthProxy path.
- ``trueconf_server_ai``: access to the TrueConf AI Server — discovery
  (``resolve_sai_base``), from-tcs token exchange + cache
  (``get_ai_token_pair``), authenticated request helper (``sai_request``).
"""

from app.mcp.auth.trueconf_server import (
    ApiTokenAuth,
    create_auth,
    create_oauth_auth,
    init_auth,
)
from app.mcp.auth.trueconf_server_ai import (
    get_ai_token_pair,
    reset_ai_auth_cache,
    resolve_sai_base,
    sai_request,
)

__all__ = [
    "ApiTokenAuth",
    "create_auth",
    "create_oauth_auth",
    "get_ai_token_pair",
    "init_auth",
    "reset_ai_auth_cache",
    "resolve_sai_base",
    "sai_request",
]
