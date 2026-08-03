import os
from dataclasses import dataclass


def _resolve_discovery_mode(explicit: str | None, code_mode_experimental: bool) -> str:
    """Resolve discovery mode from explicit choice and the legacy alias.

    ``CODE_MODE_EXPERIMENTAL`` only applies when ``DISCOVERY_MODE`` is not
    set — it must not override an explicit choice (regression guard).
    """
    if explicit is not None:
        return explicit.lower()
    if code_mode_experimental:
        return "code"
    return "static"


def _resolve_defaults(
    no_tls: bool, port: int | None, base_url: str | None
) -> tuple[int, str]:
    """Resolve the dynamic defaults for port and mcp_base_url.

    - port: 80 in plain HTTP mode, 443 in HTTPS mode (if not explicitly given).
    - base_url: built from scheme + "localhost" + port (port omitted when
      the scheme/port pair is a well-known default: http+80 or https+443).
    """
    if port is None:
        port = 80 if no_tls else 443
    if base_url is None:
        scheme = "http" if no_tls else "https"
        if (scheme, port) in (("http", 80), ("https", 443)):
            base_url = f"{scheme}://localhost"
        else:
            base_url = f"{scheme}://localhost:{port}"
    return port, base_url


def build_config(
    *,
    server: str | None,
    client_id: str | None,
    secret: str | None,
    verify_ssl: bool,
    mcp_base_url: str | None,
    port: int | None,
    no_tls: bool,
    tls_cert: str | None,
    tls_key: str | None,
    discovery_mode: str,
    auth_mode: str,
    api_token_ttl: int,
    http_timeout: float,
) -> "Config":
    """Build a Config from parsed values, validating and resolving defaults.

    Shared by the Typer ``serve()`` path and ``Config.from_env()`` so both use
    the same validation and default-resolution logic. Callers parse their
    source (CLI flags, env vars) into primitives, then delegate here.
    """
    missing = [
        name
        for name, val in (
            ("--server / TRUECONF_SERVER", server),
            ("--client-id / TRUECONF_CLIENT_ID", client_id),
            ("--secret / TRUECONF_SECRET", secret),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Provide via CLI flag, environment variable, or .env file."
        )

    if bool(tls_cert) != bool(tls_key):
        raise ValueError(
            "Both MCP_TLS_CERT and MCP_TLS_KEY are required when either is specified."
        )

    port, mcp_base_url = _resolve_defaults(no_tls, port, mcp_base_url)

    return Config(
        server=server,  # type: ignore[arg-type]
        client_id=client_id,  # type: ignore[arg-type]
        secret=secret,  # type: ignore[arg-type]
        verify_ssl=verify_ssl,
        mcp_base_url=mcp_base_url,
        port=port,
        discovery_mode=discovery_mode,
        auth_mode=auth_mode.lower(),
        api_token_ttl=api_token_ttl,
        no_tls=no_tls,
        tls_cert=tls_cert,
        tls_key=tls_key,
        http_timeout=http_timeout,
    )


@dataclass
class Config:
    server: str
    client_id: str
    secret: str
    verify_ssl: bool = True
    mcp_base_url: str = "https://localhost"
    port: int = 443
    discovery_mode: str = "static"
    auth_mode: str = "token"
    api_token_ttl: int = 86400
    no_tls: bool = False
    tls_cert: str | None = None
    tls_key: str | None = None
    http_timeout: float = 30.0

    @property
    def trueconf_base(self) -> str:
        return f"https://{self.server}"

    @property
    def login_callback_url(self) -> str:
        return f"{self.mcp_base_url}/auth/callback"

    @property
    def scheme(self) -> str:
        return "http" if self.no_tls else "https"

    @classmethod
    def from_env(cls) -> "Config":
        discovery_mode = _resolve_discovery_mode(
            explicit=os.environ.get("DISCOVERY_MODE"),
            code_mode_experimental=os.environ.get(
                "CODE_MODE_EXPERIMENTAL", "false"
            ).lower()
            == "true",
        )
        no_tls = os.environ.get("MCP_NO_TLS", "false").lower() == "true"
        port_raw = os.environ.get("TRUECONF_MCP_PORT")
        port = int(port_raw) if port_raw is not None else None
        return build_config(
            server=os.environ.get("TRUECONF_SERVER"),
            client_id=os.environ.get("TRUECONF_CLIENT_ID"),
            secret=os.environ.get("TRUECONF_SECRET"),
            verify_ssl=os.environ.get("TRUECONF_VERIFY_SSL", "true").lower() == "true",
            mcp_base_url=os.environ.get("MCP_BASE_URL") or None,
            port=port,
            no_tls=no_tls,
            tls_cert=os.environ.get("MCP_TLS_CERT") or None,
            tls_key=os.environ.get("MCP_TLS_KEY") or None,
            discovery_mode=discovery_mode,
            auth_mode=os.environ.get("AUTH_MODE", "token"),
            api_token_ttl=int(os.environ.get("API_TOKEN_TTL", "86400")),
            http_timeout=float(os.environ.get("HTTP_TIMEOUT", "30")),
        )


_config: Config | None = None


def set_config(c: Config) -> None:
    global _config
    _config = c


def get_config() -> Config:
    if _config is None:
        raise RuntimeError("Config not initialized — call set_config() first")
    return _config
