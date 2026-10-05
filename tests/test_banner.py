import io

from rich.console import Console

from app.banner import build_banner_panel, print_banner, render_logo_ansi
from app.config import Config


def _create_config(**kwargs) -> Config:
    defaults = {
        "server": "conf.example.com",
        "client_id": "test-id",
        "secret": "test-secret",
        "mcp_base_url": "https://localhost",
        "port": 443,
        "no_tls": False,
        "tls_cert": None,
        "tls_key": None,
        "discovery_mode": "static",
        "auth_mode": "token",
        "api_token_ttl": 86400,
        "http_timeout": 30.0,
    }
    defaults.update(kwargs)
    return Config(**defaults)


def test_render_logo_ansi():
    ansi = render_logo_ansi()
    assert "\x1b[1;38;2;0;192;206m" in ansi
    assert "▀" in ansi
    assert "█" in ansi
    assert "▄" in ansi


def test_banner_plain_http():
    config = _create_config(no_tls=True, port=80, mcp_base_url="http://localhost:80")
    panel = build_banner_panel(config)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    console.print(panel)
    output = buf.getvalue()

    assert "TrueConf Server MCP" in output
    assert "conf.example.com" in output
    assert "http://localhost:80/mcp" in output
    assert "off (plain HTTP)" in output
    assert "static" in output


def test_banner_tls_self_signed():
    config = _create_config(no_tls=False, port=443, mcp_base_url="https://localhost")
    panel = build_banner_panel(config)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    console.print(panel)
    output = buf.getvalue()

    assert "on (self-signed)" in output
    assert "https://localhost/mcp" in output


def test_banner_tls_custom():
    config = _create_config(
        no_tls=False,
        port=8443,
        tls_cert="/path/to/cert.pem",
        tls_key="/path/to/key.pem",
    )
    panel = build_banner_panel(config)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    console.print(panel)
    output = buf.getvalue()

    assert "on (custom cert)" in output


def test_print_banner_suppressed_by_env(monkeypatch):
    config = _create_config()
    monkeypatch.setenv("FASTMCP_SHOW_SERVER_BANNER", "false")

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    print_banner(config, console=console)

    assert buf.getvalue() == ""


def test_print_banner_default_enabled(monkeypatch):
    config = _create_config()
    monkeypatch.delenv("FASTMCP_SHOW_SERVER_BANNER", raising=False)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    print_banner(config, console=console)

    assert "TrueConf Server MCP" in buf.getvalue()
