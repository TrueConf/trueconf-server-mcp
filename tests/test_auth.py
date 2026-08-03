"""Tests for ApiTokenAuth safe refresh (T4): per-token lock + dead token removal."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from app.config import Config
from app.mcp.auth import ApiTokenAuth
from app.mcp.token_store import TokenStore


def _make_auth(mock_token_store: TokenStore) -> ApiTokenAuth:
    return ApiTokenAuth(
        token_store=mock_token_store,
        server="server.example",
        client_id="cid",
        client_secret="secret",
        verify_ssl=False,
    )


async def _create_expired_tc_token(
    store: TokenStore, *, refresh_token: str | None = "tc-refresh"
) -> str:
    """Create a token whose TrueConf access token is already expired."""
    api_token = await store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-old",
        trueconf_refresh_token=refresh_token,
        trueconf_expires_in=-10,  # already expired
    )
    return api_token.token


async def test_concurrent_verify_token_refreshes_once(
    mock_token_store: TokenStore,
) -> None:
    """Two concurrent verify_token calls with an expired TC token trigger
    exactly one refresh; both return the fresh AccessToken."""
    token = await _create_expired_tc_token(mock_token_store)
    auth = _make_auth(mock_token_store)

    refresh_calls = 0

    async def _fake_refresh(refresh_token: str) -> dict | None:
        nonlocal refresh_calls
        refresh_calls += 1
        # Hold the lock long enough for the second caller to arrive.
        await asyncio.sleep(0.05)
        return {
            "access_token": "tc-new",
            "refresh_token": "tc-new-refresh",
            "expires_in": 3600,
        }

    with patch.object(auth, "_refresh_trueconf_token", side_effect=_fake_refresh):
        results = await asyncio.gather(
            auth.verify_token(token), auth.verify_token(token)
        )

    assert refresh_calls == 1
    for r in results:
        assert r is not None
        assert r.token == "tc-new"
        assert r.client_id == "user-1"


async def test_refresh_failure_deletes_token(mock_token_store: TokenStore) -> None:
    """If refresh returns None (token revoked upstream), the record is deleted
    and a subsequent verify_token returns None."""
    token = await _create_expired_tc_token(mock_token_store)
    auth = _make_auth(mock_token_store)

    with patch.object(auth, "_refresh_trueconf_token", return_value=None):
        result = await auth.verify_token(token)
    assert result is None
    # Record was deleted from the store.
    assert await mock_token_store.get_by_token(token) is None

    # Subsequent verify_token also returns None (record gone).
    with patch.object(auth, "_refresh_trueconf_token", return_value=None):
        assert await auth.verify_token(token) is None


async def test_refresh_lock_cleaned_after_success(
    mock_token_store: TokenStore,
) -> None:
    """After a successful refresh, the per-token lock is removed from
    _refresh_locks so the dict does not grow unbounded over time."""
    token = await _create_expired_tc_token(mock_token_store)
    auth = _make_auth(mock_token_store)

    async def _fake_refresh(refresh_token: str) -> dict | None:
        return {
            "access_token": "tc-new",
            "refresh_token": "tc-new-refresh",
            "expires_in": 3600,
        }

    with patch.object(auth, "_refresh_trueconf_token", side_effect=_fake_refresh):
        result = await auth.verify_token(token)

    assert result is not None
    assert result.token == "tc-new"
    # Lock for this token must be cleaned up after a successful refresh.
    assert token not in auth._refresh_locks


async def test_refresh_lock_cleaned_after_concurrent_success(
    mock_token_store: TokenStore,
) -> None:
    """Two concurrent verify_token calls share one refresh; both return the
    fresh token and the per-token lock is cleaned up afterwards."""
    token = await _create_expired_tc_token(mock_token_store)
    auth = _make_auth(mock_token_store)

    async def _fake_refresh(refresh_token: str) -> dict | None:
        await asyncio.sleep(0.05)
        return {
            "access_token": "tc-new",
            "refresh_token": "tc-new-refresh",
            "expires_in": 3600,
        }

    with patch.object(auth, "_refresh_trueconf_token", side_effect=_fake_refresh):
        results = await asyncio.gather(
            auth.verify_token(token), auth.verify_token(token)
        )

    assert all(r is not None and r.token == "tc-new" for r in results)
    assert token not in auth._refresh_locks


async def test_cleanup_expired_removes_revoked_after_grace(
    mock_token_store: TokenStore,
) -> None:
    """cleanup_expired removes tokens with a refresh_token whose TC token
    expired more than 7 days ago (grace period)."""
    from app.mcp.token_store import ApiToken

    now = time.time()
    # TC token expired 8 days ago (beyond 7-day grace), has refresh_token.
    revoked = ApiToken(
        token="revoked-token",
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-old",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_at=now - 8 * 86400,
        created_at=now,
        expires_at=now + 3600,
    )
    await mock_token_store._store.put(key=revoked.token, value=revoked)
    idx = await mock_token_store._get_index()
    idx.tokens.append(revoked.token)
    await mock_token_store._save_index(idx)

    removed = await mock_token_store.cleanup_expired()
    assert removed >= 1
    assert await mock_token_store.get_by_token(revoked.token) is None


async def test_cleanup_expired_keeps_revoked_within_grace(
    mock_token_store: TokenStore,
) -> None:
    """A token with a refresh_token whose TC token expired recently (within
    the 7-day grace) is NOT removed — it may still be refreshed."""
    from app.mcp.token_store import ApiToken

    now = time.time()
    recent = ApiToken(
        token="recent-token",
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-old",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_at=now - 3600,  # 1h ago, within grace
        created_at=now,
        expires_at=now + 3600,
    )
    await mock_token_store._store.put(key=recent.token, value=recent)
    idx = await mock_token_store._get_index()
    idx.tokens.append(recent.token)
    await mock_token_store._save_index(idx)

    removed = await mock_token_store.cleanup_expired()
    assert removed == 0
    assert await mock_token_store.get_by_token(recent.token) is not None


# ── OAuth path disabled (B2): init_auth always returns ApiTokenAuth ──────


def test_init_auth_always_returns_api_token_auth_for_token_mode(
    mock_token_store: TokenStore,
    mock_config: Config,
) -> None:
    """init_auth with auth_mode='token' returns ApiTokenAuth (unchanged)."""
    from app.mcp.auth import init_auth, ApiTokenAuth

    mock_config.auth_mode = "token"
    auth = init_auth(mock_config, mock_token_store)
    assert isinstance(auth, ApiTokenAuth)


def test_init_auth_returns_api_token_auth_even_for_oauth_mode(
    mock_token_store: TokenStore,
    mock_config: Config,
) -> None:
    """init_auth always returns ApiTokenAuth even if auth_mode='oauth'.

    The OAuth path (OAuthProxy + _TrueConfTokenVerifier) is disabled because
    the verifier accepted any string as a valid token (auth bypass). The code
    stays as dead code for future re-enable; init_auth ignores auth_mode and
    always returns ApiTokenAuth.
    """
    from app.mcp.auth import init_auth, ApiTokenAuth

    mock_config.auth_mode = "oauth"
    auth = init_auth(mock_config, mock_token_store)
    assert isinstance(auth, ApiTokenAuth), (
        "init_auth must always return ApiTokenAuth — OAuth path is disabled"
    )
