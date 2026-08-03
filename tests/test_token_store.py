"""Tests for TokenStore token lifecycle (T3): real TTL, atomic index, <= boundary."""

from __future__ import annotations

import time

from app.mcp.token_store import TokenStore


async def test_create_token_sets_expires_at(mock_token_store: TokenStore) -> None:
    """create_token records expires_at = now + api_token_ttl."""
    before = time.time()
    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    assert api_token.expires_at >= before + mock_token_store.api_token_ttl - 1
    assert api_token.expires_at <= time.time() + mock_token_store.api_token_ttl + 1


async def test_verify_token_rejects_expired_our_token(
    mock_token_store: TokenStore,
) -> None:
    """verify_token returns None when our own token (expires_at) has expired."""
    from app.mcp.auth import ApiTokenAuth

    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    # Force our token to be expired while TrueConf token is still valid.
    api_token.expires_at = time.time() - 1
    await mock_token_store._store.put(key=api_token.token, value=api_token)

    auth = ApiTokenAuth(
        token_store=mock_token_store,
        server="server.example",
        client_id="cid",
        client_secret="secret",
        verify_ssl=False,
    )
    result = await auth.verify_token(api_token.token)
    assert result is None


async def test_create_token_updates_index_before_put(
    mock_token_store: TokenStore,
) -> None:
    """create_token saves the index BEFORE the token record (no eternal orphan).

    If _store.put fails after the index is updated, the index has a stale entry
    (get_by_token returns None, cleanup can remove it) instead of an eternal
    orphan token that is not in the index.
    """
    call_order: list[str] = []

    original_save_index = mock_token_store._save_index
    original_put = mock_token_store._store.put

    async def _tracking_save_index(index):
        call_order.append("save_index")
        return await original_save_index(index)

    async def _tracking_put(key, value):
        call_order.append("put")
        return await original_put(key, value)

    mock_token_store._save_index = _tracking_save_index  # type: ignore[assignment]
    mock_token_store._store.put = _tracking_put  # type: ignore[assignment]

    await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    # save_index must come before put
    assert call_order.index("save_index") < call_order.index("put")


async def test_cleanup_expired_removes_by_our_token_ttl(
    mock_token_store: TokenStore,
) -> None:
    """cleanup_expired removes tokens whose expires_at <= now."""
    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    # Expire our token (but keep TrueConf token valid).
    api_token.expires_at = time.time() - 1
    await mock_token_store._store.put(key=api_token.token, value=api_token)

    removed = await mock_token_store.cleanup_expired()
    assert removed == 1
    assert await mock_token_store.get_by_token(api_token.token) is None


async def test_cleanup_expired_uses_le_boundary(mock_token_store: TokenStore) -> None:
    """cleanup_expired removes tokens where trueconf_expires_at <= now (<= not <)."""
    now = time.time()
    from app.mcp.token_store import ApiToken

    # TrueConf token expired exactly now (boundary), no refresh_token.
    expired = ApiToken(
        token="expired-boundary",
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access",
        trueconf_refresh_token=None,
        trueconf_expires_at=now,
        created_at=now,
        expires_at=now + 3600,
    )
    await mock_token_store._store.put(key=expired.token, value=expired)
    idx = await mock_token_store._get_index()
    idx.tokens.append(expired.token)
    await mock_token_store._save_index(idx)

    removed = await mock_token_store.cleanup_expired()
    assert removed >= 1
    assert await mock_token_store.get_by_token(expired.token) is None


async def test_concurrent_create_token_no_lost_index(
    mock_token_store: TokenStore,
) -> None:
    """Concurrent create_token calls must not lose index entries (lock guard)."""
    import asyncio

    N = 10
    await asyncio.gather(
        *[
            mock_token_store.create_token(
                user_id=f"user-{i}",
                display_name=f"Tester-{i}",
                trueconf_access_token=f"tc-access-{i}",
                trueconf_refresh_token=f"tc-refresh-{i}",
                trueconf_expires_in=3600,
            )
            for i in range(N)
        ]
    )

    index = await mock_token_store._get_index()
    assert len(index.tokens) == N, (
        f"Expected {N} tokens in index, got {len(index.tokens)}: {index.tokens}"
    )


async def test_cleanup_expired_removes_stale_index_entries(
    mock_token_store: TokenStore,
) -> None:
    """cleanup_expired removes index entries whose record files are gone."""
    # Add a stale index entry (no corresponding record file).
    index = await mock_token_store._get_index()
    index.tokens.append("stale-orphan-token")
    await mock_token_store._save_index(index)

    # Verify it's in the index but has no record.
    assert await mock_token_store.get_by_token("stale-orphan-token") is None

    await mock_token_store.cleanup_expired()

    # The stale entry should be removed from the index.
    index = await mock_token_store._get_index()
    assert "stale-orphan-token" not in index.tokens


async def test_cleanup_expired_handles_many_tokens(
    mock_token_store: TokenStore,
) -> None:
    """cleanup_expired with many tokens removes all expired ones (O(n) set).

    Regression guard for the O(n^2) list-membership bug: with N tokens where
    half are expired, all N/2 expired tokens must be removed (not just the
    first hit) because `t.token in to_delete` was O(n) on a list and the
    later `k not in to_delete` filter silently dropped survivors.
    """
    now = time.time()
    from app.mcp.token_store import ApiToken

    # Create 6 tokens, expire 3 of them.
    for i in range(6):
        api_token = ApiToken(
            token=f"token-{i}",
            user_id=f"user-{i}",
            display_name=f"Tester-{i}",
            trueconf_access_token=f"tc-access-{i}",
            trueconf_refresh_token=f"tc-refresh-{i}",
            trueconf_expires_at=now + 3600,
            created_at=now,
            expires_at=now - 1 if i % 2 == 0 else now + 3600,
        )
        await mock_token_store._store.put(key=api_token.token, value=api_token)
        idx = await mock_token_store._get_index()
        idx.tokens.append(api_token.token)
        await mock_token_store._save_index(idx)

    removed = await mock_token_store.cleanup_expired()
    assert removed == 3, f"Expected 3 expired tokens removed, got {removed}"
    # Survivors (odd indices) must still be present.
    for i in (1, 3, 5):
        assert await mock_token_store.get_by_token(f"token-{i}") is not None
    # Expired (even indices) must be gone.
    for i in (0, 2, 4):
        assert await mock_token_store.get_by_token(f"token-{i}") is None


async def test_periodic_cleanup_runs_once_at_startup(
    mock_token_store: TokenStore, monkeypatch
) -> None:
    """periodic_cleanup runs one sweep before the first sleep (A6).

    Today the first cleanup only runs after `asyncio.sleep(3600)`, so frequent
    restarts accumulate stale tokens. The fix runs cleanup_expired() once at
    startup, then enters the hourly loop.
    """
    import asyncio
    from app.mcp import token_store as ts_module

    # Wire the global token store so periodic_cleanup can find it.
    from app.mcp import set_token_store

    set_token_store(mock_token_store)

    cleanup_calls: list[int] = []

    async def _tracking_cleanup() -> int:
        cleanup_calls.append(len(cleanup_calls))
        return 0

    monkeypatch.setattr(mock_token_store, "cleanup_expired", _tracking_cleanup)

    async def _no_sleep(_secs: float) -> None:
        # Stop the loop after the first iteration by raising CancelledError.
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    # Run periodic_cleanup; it should sweep once before sleeping, then the
    # sleep raises CancelledError which ends the loop.
    try:
        await ts_module.periodic_cleanup()
    except asyncio.CancelledError:
        pass

    assert len(cleanup_calls) >= 1, (
        "periodic_cleanup must call cleanup_expired at least once before the "
        "first sleep (startup sweep)"
    )


async def test_get_by_tc_access_token_returns_our_token(
    mock_token_store: TokenStore,
) -> None:
    """The secondary index maps trueconf_access_token to our token key."""
    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-access-1",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    result = await mock_token_store.get_by_tc_access_token("tc-access-1")
    assert result == api_token.token


async def test_get_by_tc_access_token_returns_none_for_unknown(
    mock_token_store: TokenStore,
) -> None:
    """Unknown trueconf_access_token returns None via secondary index."""
    result = await mock_token_store.get_by_tc_access_token("unknown-tc-token")
    assert result is None


async def test_tc_index_updated_on_rotation(
    mock_token_store: TokenStore,
) -> None:
    """update_trueconf_tokens updates the secondary index on token rotation."""
    api_token = await mock_token_store.create_token(
        user_id="user-1",
        display_name="Tester",
        trueconf_access_token="tc-old",
        trueconf_refresh_token="tc-refresh",
        trueconf_expires_in=3600,
    )
    await mock_token_store.update_trueconf_tokens(
        token=api_token.token,
        new_access_token="tc-new",
        new_refresh_token=None,
        new_expires_at=time.time() + 3600,
    )
    assert await mock_token_store.get_by_tc_access_token("tc-old") is None
    assert await mock_token_store.get_by_tc_access_token("tc-new") == api_token.token


async def test_cleanup_expired_handles_legacy_tokens_without_expires_at(
    mock_token_store: TokenStore,
) -> None:
    """cleanup_expired tolerates pre-T3 ApiToken records lacking `expires_at`.

    Before commit 2068148 ("feat(token-store): real TTL...") the ApiToken
    schema had no `expires_at` field. Legacy records on disk must not crash
    cleanup_expired. A legacy token with valid TrueConf credentials survives
    (default expires_at=+inf preserves pre-T3 behavior); one whose TrueConf
    token has expired and has no refresh_token is removed.
    """
    underlying = mock_token_store._store._key_value

    # Legacy token with VALID TrueConf credentials — must SURVIVE.
    valid_legacy = {
        "token": "legacy-valid",
        "user_id": "user-1",
        "display_name": "Tester",
        "trueconf_access_token": "tc-valid",
        "trueconf_refresh_token": "tc-refresh-valid",
        "trueconf_expires_at": time.time() + 3600,
        "created_at": time.time() - 9999,
        "request_count": 0,
    }
    await underlying.put(
        key="legacy-valid", value=valid_legacy, collection="mcp-api-tokens"
    )
    # Legacy token with EXPIRED TrueConf credentials, no refresh — must be REMOVED.
    dead_legacy = {
        "token": "legacy-dead",
        "user_id": "user-2",
        "display_name": "Tester",
        "trueconf_access_token": "tc-dead",
        "trueconf_refresh_token": None,
        "trueconf_expires_at": time.time() - 9999,
        "created_at": time.time() - 9999,
        "request_count": 0,
    }
    await underlying.put(
        key="legacy-dead", value=dead_legacy, collection="mcp-api-tokens"
    )
    idx = await mock_token_store._get_index()
    idx.tokens.extend(["legacy-valid", "legacy-dead"])
    await mock_token_store._save_index(idx)

    removed = await mock_token_store.cleanup_expired()
    assert removed == 1
    assert await mock_token_store.get_by_token("legacy-valid") is not None
    assert await mock_token_store.get_by_token("legacy-dead") is None
