import asyncio
import enum
import logging
import os
import sys
from typing import Annotated

from dotenv import load_dotenv
import typer

from app.config import Config, build_config, _resolve_discovery_mode, set_config
from app.mcp.auth import init_auth
from app.mcp import mcp, set_token_store, init_http_client, close_http_client
from app.mcp.token_store import init_token_store, periodic_cleanup
import app.mcp.tools.conferences  # noqa: F401 — triggers tool registration
import app.mcp.prompts  # noqa: F401 — triggers prompt registration
import app.mcp.routes  # noqa: F401 — triggers custom route registration
from app.mcp.routes import register_login_callback
from app.mcp.i18n import init_i18n
from app.mcp.instructions import apply_discovery_mode
from app.tls import bind_error_help, resolve_tls_files

# Load .env into os.environ BEFORE Typer parses envvars. App modules no longer
# read env at import time (they use get_config()), so order is safe.
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_i18n()


# ── Server bootstrap ──────────────────────────────────────────────────────


async def _serve(port: int, tls_files: tuple[str, str] | None) -> None:
    """Run the MCP HTTP server with periodic cleanup background task.

    When `tls_files` is None, the server runs plain HTTP. Otherwise it runs
    HTTPS with the given (cert_path, key_path).
    """
    cleanup_task = asyncio.create_task(periodic_cleanup())
    try:
        uvicorn_config: dict = {}
        if tls_files is not None:
            cert_path, key_path = tls_files
            uvicorn_config["ssl_certfile"] = cert_path
            uvicorn_config["ssl_keyfile"] = key_path

        try:
            await mcp.run_http_async(
                transport="http",
                host="0.0.0.0",
                port=port,
                uvicorn_config=uvicorn_config,
            )
        except (PermissionError, OSError) as e:
            # Bind failure on a privileged port — surface a actionable message
            # instead of a raw traceback.
            if "Permission denied" in str(e) or e.errno == 13:
                typer.secho(bind_error_help(port), err=True, fg=typer.colors.RED)
                raise SystemExit(1)
            raise
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await close_http_client()


def run_server(config: Config) -> None:
    """Initialize and run the TrueConf Server MCP.

    Sets config, builds token store + auth, applies discovery mode, registers
    the conditional /auth/callback route (token mode only), and starts the
    HTTP server. Blocks until the server stops.
    """
    set_config(config)
    logger.info("AUTH_MODE=%s", config.auth_mode)

    init_http_client()

    token_store = init_token_store(config)
    set_token_store(token_store)

    auth = init_auth(config, token_store)

    transforms = apply_discovery_mode(config)

    mcp.auth = auth
    for t in transforms:
        mcp.add_transform(t)

    # /auth/callback is always registered — token mode is the only active
    # auth mode (OAuth path disabled, see init_auth).
    register_login_callback()

    tls_files = resolve_tls_files(config)
    scheme = "http" if config.no_tls else "https"
    logger.info(
        "Serving on %s://0.0.0.0:%d (mcp_base_url=%s, tls=%s)",
        scheme,
        config.port,
        config.mcp_base_url,
        "off" if tls_files is None else "on",
    )

    try:
        asyncio.run(_serve(config.port, tls_files))
    except KeyboardInterrupt:
        logger.info("Server stopped by user")


class DiscoveryMode(str, enum.Enum):
    static = "static"
    bm25 = "bm25"
    code = "code"


class AuthMode(str, enum.Enum):
    """Only 'token' is active. OAuth path is disabled (see init_auth)."""

    token = "token"


app = typer.Typer(
    help="TrueConf Server MCP — manage conferences, recordings, invitations "
    "and other TrueConf Server objects via the Model Context Protocol.",
    no_args_is_help=True,
)


@app.command()
def serve(
    server: Annotated[
        str | None,
        typer.Option("--server", envvar="TRUECONF_SERVER", help="TrueConf Server host"),
    ] = None,
    client_id: Annotated[
        str | None,
        typer.Option(
            "--client-id", envvar="TRUECONF_CLIENT_ID", help="OAuth client_id"
        ),
    ] = None,
    secret: Annotated[
        str | None,
        typer.Option(
            "--client-secret", envvar="TRUECONF_SECRET", help="OAuth client_secret"
        ),
    ] = None,
    verify_ssl: Annotated[
        bool,
        typer.Option(
            "--verify-ssl/--no-verify-ssl",
            envvar="TRUECONF_VERIFY_SSL",
            help="Verify TrueConf Server SSL certificate",
        ),
    ] = True,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            envvar="MCP_BASE_URL",
            help="Public URL of this MCP server (must be reachable by MCP clients). "
            "Default: https://localhost (https://localhost:<port> if --port is custom), "
            "http://localhost when --no-tls.",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            envvar="TRUECONF_MCP_PORT",
            help="Listen port. Default: 443 (HTTPS) or 80 with --no-tls.",
        ),
    ] = None,
    no_tls: Annotated[
        bool,
        typer.Option(
            "--no-tls",
            envvar="MCP_NO_TLS",
            help="Disable TLS — serve plain HTTP instead of HTTPS. "
            "Default port becomes 80.",
        ),
    ] = False,
    tls_cert: Annotated[
        str | None,
        typer.Option(
            "--tls-cert",
            envvar="MCP_TLS_CERT",
            help="Path to a custom TLS certificate (PEM). Requires --tls-key. "
            "If omitted with TLS enabled, a self-signed cert is generated.",
        ),
    ] = None,
    tls_key: Annotated[
        str | None,
        typer.Option(
            "--tls-key",
            envvar="MCP_TLS_KEY",
            help="Path to a custom TLS private key (PEM). Requires --tls-cert.",
        ),
    ] = None,
    discovery_mode: Annotated[
        DiscoveryMode,
        typer.Option(
            "--discovery-mode",
            envvar="DISCOVERY_MODE",
            help="Tool discovery: static (all tools), bm25 (search gateway), code (CodeMode sandbox)",
        ),
    ] = DiscoveryMode.static,
    auth_mode: Annotated[
        AuthMode,
        typer.Option(
            "--auth-mode",
            envvar="AUTH_MODE",
            help="Auth mode: token (manual long-lived token). OAuth path is disabled.",
        ),
    ] = AuthMode.token,
    api_token_ttl: Annotated[
        int,
        typer.Option(
            "--api-token-ttl",
            envvar="API_TOKEN_TTL",
            help="TTL of our API token (seconds)",
        ),
    ] = 86400,
    http_timeout: Annotated[
        float,
        typer.Option(
            "--http-timeout",
            envvar="HTTP_TIMEOUT",
            help="Timeout (seconds) for TrueConf API HTTP requests",
        ),
    ] = 30.0,
) -> None:
    """Start the TrueConf Server MCP.

    Configuration priority (highest to lowest):
      1. CLI flags (--server, --port, ...)
      2. Environment variables (TRUECONF_SERVER, TRUECONF_MCP_PORT, ...)
      3. .env file (loaded via python-dotenv)
      4. Built-in defaults
    """
    # Resolve discovery mode: explicit CLI flag or DISCOVERY_MODE env wins
    # over the legacy CODE_MODE_EXPERIMENTAL alias (regression guard —
    # previously CODE_MODE_EXPERIMENTAL=true overrode DISCOVERY_MODE=bm25 set
    # via env because only sys.argv was checked for explicitness).
    discovery_mode_explicit_cli = any(
        arg == "--discovery-mode" or arg.startswith("--discovery-mode=")
        for arg in sys.argv
    )
    if discovery_mode_explicit_cli or os.environ.get("DISCOVERY_MODE") is not None:
        resolved_discovery_mode = discovery_mode.value
    else:
        resolved_discovery_mode = _resolve_discovery_mode(
            explicit=None,
            code_mode_experimental=os.environ.get(
                "CODE_MODE_EXPERIMENTAL", "false"
            ).lower()
            == "true",
        )
        if resolved_discovery_mode == "code":
            logger.warning(
                "CODE_MODE_EXPERIMENTAL is deprecated — use DISCOVERY_MODE=code instead"
            )

    try:
        config = build_config(
            server=server,
            client_id=client_id,
            secret=secret,
            verify_ssl=verify_ssl,
            mcp_base_url=base_url,
            port=port,
            no_tls=no_tls,
            tls_cert=tls_cert,
            tls_key=tls_key,
            discovery_mode=resolved_discovery_mode,
            auth_mode=auth_mode.value,
            api_token_ttl=api_token_ttl,
            http_timeout=http_timeout,
        )
    except RuntimeError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except ValueError as e:
        raise typer.BadParameter(str(e))

    run_server(config)


if __name__ == "__main__":
    app()
