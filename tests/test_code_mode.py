"""Tests for code_mode guide (T10): uses Config instead of os.environ."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import Config, set_config


@pytest.fixture
def _custom_config() -> Config:
    cfg = Config(
        server="server.example",
        client_id="cid",
        secret="secret",
        verify_ssl=False,
        mcp_base_url="https://10.100.2.108",
        port=443,
    )
    set_config(cfg)
    return cfg


async def test_guide_uses_config_base_url(_custom_config: Config) -> None:
    """guide() returns the Config mcp_base_url, not os.environ default."""
    from app.mcp.code_mode import _make_guide

    guide_tool = _make_guide(None)
    fn = guide_tool.fn
    with patch.dict("os.environ", {"MCP_BASE_URL": "https://localhost"}, clear=False):
        result = await fn(None)  # type: ignore[arg-type]
    assert "https://10.100.2.108/" in result
    assert "https://localhost" not in result


async def test_guide_handles_uninitialized_config() -> None:
    """guide() does not crash when Config is not initialized — graceful fallback."""
    import app.config as cfg_mod
    from app.mcp.code_mode import _make_guide

    original = cfg_mod._config
    cfg_mod._config = None
    try:
        guide_tool = _make_guide(None)
        fn = guide_tool.fn
        result = await fn(None)  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert "TrueConf Server MCP" in result
    finally:
        cfg_mod._config = original
