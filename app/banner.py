from __future__ import annotations

import os
from typing import TYPE_CHECKING

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from app.config import Config

try:
    from app._version import __version__
except ImportError:
    __version__ = "unknown"

# 2-row block micro-font for "TRUECONF"
LOGO_LINES = (
    "▀█▀ █▀█ █ █ █▀▀ █▀▀ █▀█ █▀█ █▀▀",
    " █  █▀▄ █▄█ ██▄ █▄▄ █▄█ █ █ █▀ ",
)

# TrueConf corporate cyan (#00C0CE) from trueconf.ru (buttons, icons, active highlights)
BRAND_COLOR_HEX = "#00C0CE"
BRAND_COLOR_RGB = (0, 192, 206)

REPO_URL = "https://github.com/TrueConf/trueconf-server-mcp"


def render_logo_ansi(
    lines: tuple[str, ...] = LOGO_LINES,
    color_rgb: tuple[int, int, int] = BRAND_COLOR_RGB,
) -> str:
    """Generate ANSI 24-bit color string for the logo in bold TrueConf #00C0CE."""
    r, g, b = color_rgb
    color_code = f"\x1b[1;38;2;{r};{g};{b}m"
    return "\n".join(f"{color_code}{line}\x1b[0m" for line in lines)


def build_banner_panel(config: Config) -> Panel:
    """Build the Rich Panel containing the TrueConf Server MCP startup banner."""
    logo_ansi = render_logo_ansi()
    logo_text = Text.from_ansi(logo_ansi, no_wrap=True)

    title_text = Text(f"TrueConf Server MCP {__version__}", style=f"bold {BRAND_COLOR_HEX}")
    repo_text = Text(REPO_URL, style="dim")

    info_table = Table.grid(padding=(0, 1))
    info_table.add_column(style="bold", justify="center")
    info_table.add_column(style=f"bold {BRAND_COLOR_HEX}", justify="left")
    info_table.add_column(style="dim", justify="left")

    info_table.add_row("🖥", "TrueConf Server:", config.server)
    info_table.add_row("🌐", "MCP Endpoint:", f"{config.mcp_base_url.rstrip('/')}/mcp")

    if config.no_tls:
        tls_info = "off (plain HTTP)"
    elif config.tls_cert:
        tls_info = "on (custom cert)"
    else:
        tls_info = "on (self-signed)"
    info_table.add_row("🔒", "TLS:", tls_info)

    info_table.add_row("🚀", "Discovery Mode:", config.discovery_mode)

    panel_content = Group(
        "",
        Align.center(logo_text),
        "",
        Align.center(title_text),
        Align.center(repo_text),
        "",
        Align.center(info_table),
        "",
    )

    return Panel(
        panel_content,
        border_style="dim",
        padding=(1, 4),
        width=80,
    )


def print_banner(config: Config, console: Console | None = None) -> None:
    """Print the startup banner to stderr (matching FastMCP's console convention)."""
    if os.environ.get("FASTMCP_SHOW_SERVER_BANNER", "true").lower() in {"false", "0", "no"}:
        return

    if console is None:
        console = Console(stderr=True)

    panel = build_banner_panel(config)
    console.print(Align.center(panel))
