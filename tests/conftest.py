"""Shared pytest fixtures for async tests.

Provides reusable building blocks for testing the async paths that were
previously structurally untestable: TokenStore (on a tmp directory), the
``_request`` helper (with a mocked httpx transport), Config factories, and
AccessToken/ApiToken factories.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp.server.auth import AccessToken

from app.config import Config, set_config
from app.mcp.token_store import ApiToken, TokenStore, TCTokenIndex


class FakeRequest:
    """Minimal stand-in for starlette.requests.Request (shared by test modules)."""

    def __init__(
        self,
        *,
        method: str = "GET",
        cookies: dict | None = None,
        query_params: dict | None = None,
        headers: dict | None = None,
    ) -> None:
        self.method = method
        self.cookies = cookies or {}
        self.query_params = query_params or {}
        self.headers = headers or {}


@pytest.fixture
def tmp_storage_dir(tmp_path: Path) -> Path:
    """A per-test directory for file-backed stores."""
    return tmp_path / "token-store"


def _build_file_store(storage_dir: Path) -> TokenStore:
    """Build a real (non-encrypted) FileTreeStore-backed TokenStore for tests."""
    from key_value.aio.stores.filetree import (
        FileTreeStore,
        FileTreeV1CollectionSanitizationStrategy,
        FileTreeV1KeySanitizationStrategy,
    )
    from key_value.aio.adapters.pydantic import PydanticAdapter

    storage_dir.mkdir(parents=True, exist_ok=True)
    file_store = FileTreeStore(
        data_directory=storage_dir,
        key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(storage_dir),
        collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(
            storage_dir
        ),
    )
    # TokenStore.__init__ wraps client_storage in PydanticAdapter itself; pass
    # the raw file store directly (no encryption in tests).
    store = TokenStore.__new__(TokenStore)
    store.api_token_ttl = 3600
    store._store = PydanticAdapter(
        key_value=file_store,
        pydantic_model=ApiToken,
        default_collection="mcp-api-tokens",
        raise_on_validation_error=True,
    )
    from key_value.aio.adapters.pydantic import PydanticAdapter as _PA
    from app.mcp.token_store import TokenIndex

    store._index_store = _PA(
        key_value=file_store,
        pydantic_model=TokenIndex,
        default_collection="mcp-api-tokens",
        raise_on_validation_error=True,
    )
    store._tc_index_store = _PA(
        key_value=file_store,
        pydantic_model=TCTokenIndex,
        default_collection="mcp-api-tokens",
        raise_on_validation_error=True,
    )
    store._index_lock = asyncio.Lock()
    return store


@pytest.fixture
def mock_config() -> Config:
    """A Config with safe test values (verify_ssl off, short TTL)."""
    return Config(
        server="server.example",
        client_id="test-client-id",
        secret="test-secret",
        verify_ssl=False,
        mcp_base_url="https://localhost",
        port=443,
        auth_mode="token",
        api_token_ttl=3600,
    )


@pytest.fixture
def mock_config_set(mock_config: Config) -> Config:
    """Config that is also registered globally via set_config()."""
    set_config(mock_config)
    return mock_config


@pytest.fixture
def mock_token_store(tmp_storage_dir: Path) -> TokenStore:
    """A TokenStore backed by a tmp directory (no encryption)."""
    return _build_file_store(tmp_storage_dir)


@pytest.fixture
def mock_access_token() -> AccessToken:
    """A FastMCP AccessToken with test values."""
    return AccessToken(
        token="trueconf-access-token-test", client_id="user-1", scopes=[]
    )


@pytest.fixture
def mock_httpx_response():
    """Factory that builds httpx.Response objects with configurable content."""

    def _make(
        status_code: int = 200,
        json_data: Any | None = None,
        text: str | None = None,
        content_type: str = "application/json",
    ) -> httpx.Response:
        if json_data is not None:
            return httpx.Response(status_code, json=json_data)
        if text is not None:
            return httpx.Response(
                status_code,
                text=text,
                headers={"content-type": content_type},
            )
        return httpx.Response(
            status_code, json={}, headers={"content-type": content_type}
        )

    return _make


@pytest.fixture(scope="session")
def _init_i18n():
    """Load i18n translations once per session.

    Shared across test modules so ``init_i18n()`` (which locks the loader)
    is called exactly once.
    """
    from app.mcp.i18n import init_i18n

    init_i18n()
