from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time

from fastmcp import settings
from fastmcp.server.auth.jwt_issuer import derive_jwt_key
from cryptography.fernet import Fernet
from pydantic import BaseModel
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.adapters.pydantic import PydanticAdapter
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from app.config import Config
from app.mcp.logging_utils import mask_token

logger = logging.getLogger(__name__)


class ApiToken(BaseModel):
    """Mapping from our external token to TrueConf Server credentials.

    Our token expires at ``expires_at`` (now + api_token_ttl at creation).
    TrueConf tokens are refreshed transparently on the server side.
    """

    token: str
    user_id: str
    display_name: str
    trueconf_access_token: str
    trueconf_refresh_token: str | None
    trueconf_expires_at: float
    created_at: float
    # Default +inf tolerates pre-T3 records on disk that predate this field
    # (commit 2068148 added it). Legacy tokens never expire by our TTL
    # (preserving pre-T3 behavior); cleanup only removes them when their
    # TrueConf credentials are actually dead (tc_expired / tc_revoked).
    # New tokens always get an explicit expires_at from create_token.
    expires_at: float = float("inf")


class TokenIndex(BaseModel):
    """Index of all token keys for enumeration."""

    tokens: list[str] = []


class TCTokenIndex(BaseModel):
    """Reverse index: trueconf_access_token -> our token key (O(1) refresh lookup)."""

    mappings: dict[str, str] = {}


class TokenStore:
    """Persistent storage for API token → TrueConf credential mappings.

    Uses the same encrypted file store as OAuthProxy:
    ~/Library/Application Support/fastmcp/oauth-proxy/<fingerprint>/mcp-api-tokens/
    """

    _INDEX_KEY = "__token_index__"
    _TC_INDEX_KEY = "__tc_token_index__"

    def __init__(
        self, client_storage: AsyncKeyValue, api_token_ttl: int = 86400
    ) -> None:
        self.api_token_ttl = api_token_ttl
        self._store: PydanticAdapter[ApiToken] = PydanticAdapter(
            key_value=client_storage,
            pydantic_model=ApiToken,
            default_collection="mcp-api-tokens",
            raise_on_validation_error=True,
        )
        self._index_store: PydanticAdapter[TokenIndex] = PydanticAdapter(
            key_value=client_storage,
            pydantic_model=TokenIndex,
            default_collection="mcp-api-tokens",
            raise_on_validation_error=True,
        )
        self._tc_index_store: PydanticAdapter[TCTokenIndex] = PydanticAdapter(
            key_value=client_storage,
            pydantic_model=TCTokenIndex,
            default_collection="mcp-api-tokens",
            raise_on_validation_error=True,
        )
        self._index_lock = asyncio.Lock()

    async def _get_index(self) -> TokenIndex:
        idx = await self._index_store.get(key=self._INDEX_KEY)
        return idx if idx else TokenIndex(tokens=[])

    async def _save_index(self, index: TokenIndex) -> None:
        await self._index_store.put(key=self._INDEX_KEY, value=index)

    async def _get_tc_index(self) -> TCTokenIndex:
        idx = await self._tc_index_store.get(key=self._TC_INDEX_KEY)
        return idx if idx else TCTokenIndex(mappings={})

    async def _save_tc_index(self, index: TCTokenIndex) -> None:
        await self._tc_index_store.put(key=self._TC_INDEX_KEY, value=index)

    async def get_by_tc_access_token(self, trueconf_access_token: str) -> str | None:
        """O(1) lookup: trueconf_access_token -> our token key (or None)."""
        tc_index = await self._get_tc_index()
        return tc_index.mappings.get(trueconf_access_token)

    async def create_token(
        self,
        user_id: str,
        display_name: str,
        trueconf_access_token: str,
        trueconf_refresh_token: str | None,
        trueconf_expires_in: int,
    ) -> ApiToken:
        token = secrets.token_urlsafe(32)
        now = time.time()
        api_token = ApiToken(
            token=token,
            user_id=user_id,
            display_name=display_name,
            trueconf_access_token=trueconf_access_token,
            trueconf_refresh_token=trueconf_refresh_token,
            trueconf_expires_at=now + trueconf_expires_in,
            created_at=now,
            expires_at=now + self.api_token_ttl,
        )
        # Save the index BEFORE the record: a crash between the two leaves a
        # stale index entry (get_by_token returns None, cleanup removes it)
        # rather than an eternal orphan record that is not in the index.
        async with self._index_lock:
            index = await self._get_index()
            index.tokens.append(token)
            await self._save_index(index)
            tc_index = await self._get_tc_index()
            tc_index.mappings[trueconf_access_token] = token
            await self._save_tc_index(tc_index)
            await self._store.put(key=token, value=api_token)

        logger.info(
            "Created API token for user=%s token=%s", user_id, mask_token(token)
        )
        return api_token

    async def get_by_token(self, token: str) -> ApiToken | None:
        return await self._store.get(key=token)

    async def update_trueconf_tokens(
        self,
        token: str,
        new_access_token: str,
        new_refresh_token: str | None,
        new_expires_at: float,
    ) -> None:
        async with self._index_lock:
            record = await self._store.get(key=token)
            if not record:
                return
            old_tc_token = record.trueconf_access_token
            record.trueconf_access_token = new_access_token
            if new_refresh_token:
                record.trueconf_refresh_token = new_refresh_token
            record.trueconf_expires_at = new_expires_at
            await self._store.put(key=token, value=record)
            # Update the TC index if the access token rotated.
            if old_tc_token != new_access_token:
                tc_index = await self._get_tc_index()
                tc_index.mappings.pop(old_tc_token, None)
                tc_index.mappings[new_access_token] = token
                await self._save_tc_index(tc_index)
        logger.info("Updated TrueConf tokens for user=%s", record.user_id)

    async def get_all_tokens(self) -> list[ApiToken]:
        """Get all tokens (for admin)."""
        index = await self._get_index()
        if not index.tokens:
            return []
        records = await self._store.get_many(keys=index.tokens)
        return [r for r in records if r is not None]

    async def delete(self, token: str) -> None:
        """Delete a single token record and remove it from all indexes."""
        async with self._index_lock:
            record = await self._store.get(key=token)
            await self._store.delete(key=token)
            index = await self._get_index()
            if token in index.tokens:
                index.tokens = [k for k in index.tokens if k != token]
                await self._save_index(index)
            if record is not None:
                tc_index = await self._get_tc_index()
                tc_index.mappings.pop(record.trueconf_access_token, None)
                await self._save_tc_index(tc_index)

    async def cleanup_expired(self) -> int:
        """Delete tokens that have expired.

        Removes:
        - Our own tokens whose ``expires_at <= now`` (our TTL elapsed).
        - TrueConf tokens whose ``trueconf_expires_at <= now`` with no
          ``refresh_token`` (can't be renewed).
        - TrueConf tokens whose ``trueconf_expires_at`` expired more than 7
          days ago AND have a ``refresh_token`` (grace period elapsed — the
          refresh_token is almost certainly revoked upstream).

        Both immediate checks use ``<=`` so the boundary is consistent with
        ``ApiTokenAuth.verify_token``.
        """
        async with self._index_lock:
            now = time.time()
            grace = 7 * 86400
            all_tokens = await self.get_all_tokens()
            to_delete: set[str] = set()

            for t in all_tokens:
                own_expired = t.expires_at <= now
                tc_expired = (
                    t.trueconf_expires_at <= now and not t.trueconf_refresh_token
                )
                tc_revoked = (
                    t.trueconf_refresh_token and t.trueconf_expires_at < now - grace
                )
                if own_expired or tc_expired or tc_revoked:
                    to_delete.add(t.token)

            if to_delete:
                for key in to_delete:
                    await self._store.delete(key=key)
            # Build a set of TC access tokens to remove from the secondary index.
            tc_to_remove = {
                t.trueconf_access_token for t in all_tokens if t.token in to_delete
            }
            index = await self._get_index()
            # Remove expired tokens AND stale entries (no record file).
            records = await self._store.get_many(keys=index.tokens)
            surviving_keys = {
                k
                for k, r in zip(index.tokens, records)
                if r is not None and k not in to_delete
            }
            index.tokens = list(surviving_keys)
            await self._save_index(index)
            # Clean TC index: remove deleted tokens' mappings and stale entries.
            tc_index = await self._get_tc_index()
            tc_index.mappings = {
                tc: our_key
                for tc, our_key in tc_index.mappings.items()
                if our_key in surviving_keys and tc not in tc_to_remove
            }
            await self._save_tc_index(tc_index)
        if to_delete:
            logger.info("Cleaned up %d expired tokens", len(to_delete))

        return len(to_delete)


# ── Bootstrap & lifecycle ──────────────────────────────────────────────────


def init_token_store(config: Config) -> TokenStore:
    """Initialize the shared encrypted token store."""
    _signing_key = derive_jwt_key(
        high_entropy_material=config.secret,
        salt="fastmcp-jwt-signing-key",
    )
    _storage_key = derive_jwt_key(
        high_entropy_material=_signing_key.decode(),
        salt="fastmcp-storage-encryption-key",
    )
    _key_fingerprint = hashlib.sha256(_storage_key).hexdigest()[:12]
    _storage_dir = settings.home / "oauth-proxy" / _key_fingerprint
    _storage_dir.mkdir(parents=True, exist_ok=True)

    _file_store = FileTreeStore(
        data_directory=_storage_dir,
        key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(_storage_dir),
        collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(
            _storage_dir
        ),
    )
    client_storage = FernetEncryptionWrapper(
        key_value=_file_store,
        fernet=Fernet(key=_storage_key),
        raise_on_decryption_error=False,
    )
    return TokenStore(client_storage=client_storage, api_token_ttl=config.api_token_ttl)


async def periodic_cleanup() -> None:
    """Hourly background task: delete expired TrueConf tokens without refresh.

    Runs one sweep immediately at startup (before the first sleep) so that
    stale tokens accumulated during downtime are cleaned promptly, then
    enters the hourly loop.

    Note: `TokenStore.cleanup_expired()` already logs the count; this wrapper
    does not log again to avoid duplicate log lines.
    """
    from app.mcp import get_token_store

    # Startup sweep: clean stale tokens accumulated before this process started.
    try:
        token_store = get_token_store()
        if token_store is not None:
            await token_store.cleanup_expired()
    except Exception as e:
        logger.exception("Startup cleanup error: %s", e)

    while True:
        await asyncio.sleep(3600)
        try:
            token_store = get_token_store()
            if token_store is not None:
                await token_store.cleanup_expired()
        except Exception as e:
            logger.exception("Periodic cleanup error: %s", e)
