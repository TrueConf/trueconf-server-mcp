import os
from unittest.mock import patch

import pytest

from app.config import Config, _resolve_defaults, build_config, _resolve_discovery_mode


@pytest.mark.parametrize(
    "no_tls, port, base_url, expected_port, expected_base_url",
    [
        # HTTPS default: 443, https://localhost (port omitted)
        (False, None, None, 443, "https://localhost"),
        # HTTP default (--no-tls): 80, http://localhost (port omitted)
        (True, None, None, 80, "http://localhost"),
        # HTTPS with custom port: port kept, included in URL
        (False, 8443, None, 8443, "https://localhost:8443"),
        # HTTP with custom port: port kept, included in URL
        (True, 8080, None, 8080, "http://localhost:8080"),
        # Explicit base_url always wins
        (False, None, "https://10.100.2.108", 443, "https://10.100.2.108"),
        (True, None, "http://conf.local", 80, "http://conf.local"),
        # Explicit base_url with custom port
        (False, 9000, "https://example.com", 9000, "https://example.com"),
        # --no-tls with port 443: port IS included (http on 443 is non-default)
        (True, 443, None, 443, "http://localhost:443"),
        # TLS with port 80: port IS included (https on 80 is non-default)
        (False, 80, None, 80, "https://localhost:80"),
    ],
)
def test_resolve_defaults(no_tls, port, base_url, expected_port, expected_base_url):
    port_out, base_url_out = _resolve_defaults(no_tls, port, base_url)
    assert port_out == expected_port
    assert base_url_out == expected_base_url


def _set_env(**kwargs):
    """Set env vars for from_env tests, with required defaults."""
    env = {
        "TRUECONF_SERVER": "server.example",
        "TRUECONF_CLIENT_ID": "cid",
        "TRUECONF_SECRET": "secret",
    }
    env.update(kwargs)
    return patch.dict(os.environ, env, clear=True)


def test_from_env_code_mode_experimental_does_not_override_discovery_mode():
    """CODE_MODE_EXPERIMENTAL=true must NOT override explicit DISCOVERY_MODE."""
    with _set_env(CODE_MODE_EXPERIMENTAL="true", DISCOVERY_MODE="bm25"):
        cfg = Config.from_env()
    assert cfg.discovery_mode == "bm25"


def test_from_env_code_mode_experimental_applies_when_no_discovery_mode():
    """CODE_MODE_EXPERIMENTAL=true applies when DISCOVERY_MODE is not set."""
    with _set_env(CODE_MODE_EXPERIMENTAL="true"):
        cfg = Config.from_env()
    assert cfg.discovery_mode == "code"


def test_from_env_auth_mode_is_lowercased():
    """AUTH_MODE=Token (capitalized) is lowercased to 'token'."""
    with _set_env(AUTH_MODE="Token"):
        cfg = Config.from_env()
    assert cfg.auth_mode == "token"


def test_from_env_tls_cert_without_key_raises():
    """Config.from_env validates tls_cert/tls_key pair."""
    with _set_env(MCP_TLS_CERT="/path/cert.pem"):
        with pytest.raises(ValueError, match="MCP_TLS_CERT.*MCP_TLS_KEY"):
            Config.from_env()


def test_from_env_tls_key_without_cert_raises():
    """Config.from_env validates tls_cert/tls_key pair (reverse)."""
    with _set_env(MCP_TLS_KEY="/path/key.pem"):
        with pytest.raises(ValueError, match="MCP_TLS_CERT.*MCP_TLS_KEY"):
            Config.from_env()


def test_from_env_missing_server_raises_friendly_error():
    """Missing TRUECONF_SERVER raises a clear error, not raw KeyError."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises((ValueError, RuntimeError)):
            Config.from_env()


def test_from_env_http_timeout_from_env():
    """http_timeout is read from HTTP_TIMEOUT env var."""
    with _set_env(HTTP_TIMEOUT="60"):
        cfg = Config.from_env()
    assert cfg.http_timeout == 60.0


def test_from_env_http_timeout_default():
    """http_timeout defaults to 30.0."""
    with _set_env():
        cfg = Config.from_env()
    assert cfg.http_timeout == 30.0


# ── build_config: shared builder used by both Typer and from_env ─────────


def _build_kwargs(**overrides):
    """Minimal valid kwargs for build_config; override as needed per test."""
    base = dict(
        server="server.example",
        client_id="cid",
        secret="secret",
        verify_ssl=True,
        mcp_base_url=None,
        port=None,
        no_tls=False,
        tls_cert=None,
        tls_key=None,
        discovery_mode="static",
        auth_mode="token",
        api_token_ttl=86400,
        http_timeout=30.0,
    )
    base.update(overrides)
    return base


def test_build_config_resolves_defaults():
    """build_config resolves port and mcp_base_url from no_tls/port/base_url."""
    cfg = build_config(**_build_kwargs())
    assert cfg.port == 443
    assert cfg.mcp_base_url == "https://localhost"


def test_build_config_missing_server_raises_runtime_error():
    """build_config raises RuntimeError listing the missing required field."""
    with pytest.raises(RuntimeError, match="server"):
        build_config(**_build_kwargs(server=None))


def test_build_config_missing_client_id_raises():
    with pytest.raises(RuntimeError, match="client"):
        build_config(**_build_kwargs(client_id=None))


def test_build_config_missing_secret_raises():
    with pytest.raises(RuntimeError, match="secret"):
        build_config(**_build_kwargs(secret=None))


def test_build_config_tls_cert_without_key_raises():
    with pytest.raises(ValueError, match="MCP_TLS_CERT.*MCP_TLS_KEY"):
        build_config(**_build_kwargs(tls_cert="/path/cert.pem"))


def test_build_config_tls_key_without_cert_raises():
    with pytest.raises(ValueError, match="MCP_TLS_CERT.*MCP_TLS_KEY"):
        build_config(**_build_kwargs(tls_key="/path/key.pem"))


def test_build_config_lowercases_auth_mode():
    cfg = build_config(**_build_kwargs(auth_mode="Token"))
    assert cfg.auth_mode == "token"


# ── _resolve_discovery_mode: shared discovery-mode resolution ────────────


def test_resolve_discovery_mode_explicit_wins_over_code_mode_experimental():
    """Explicit DISCOVERY_MODE must not be overridden by CODE_MODE_EXPERIMENTAL."""
    assert (
        _resolve_discovery_mode(explicit="bm25", code_mode_experimental=True) == "bm25"
    )


def test_resolve_discovery_mode_code_mode_experimental_when_no_explicit():
    assert _resolve_discovery_mode(explicit=None, code_mode_experimental=True) == "code"


def test_resolve_discovery_mode_default_static():
    assert (
        _resolve_discovery_mode(explicit=None, code_mode_experimental=False) == "static"
    )


def test_resolve_discovery_mode_lowercases_explicit():
    assert (
        _resolve_discovery_mode(explicit="BM25", code_mode_experimental=False) == "bm25"
    )
