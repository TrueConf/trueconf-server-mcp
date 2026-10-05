"""HTTP client for the TrueConf AI Server user API.

Pure domain layer: every function takes an ``httpx.AsyncClient`` (the shared
client from ``app.mcp`` works — absolute URLs override its base_url) and an
explicit ``sai_base`` like ``https://sai01t.trueconf.name``. No MCP imports.
"""

import logging
from typing import Any

import httpx

from app._client_api._trueconf_server_ai.models import AiTokenPair

logger = logging.getLogger(__name__)

_V1 = "/api/user/v1"


class AiApiError(Exception):
    """Non-2xx response from the AI Server."""

    def __init__(self, status_code: int, description: str):
        self.status_code = status_code
        self.description = description
        super().__init__(f"HTTP {status_code}: {description}")


def _error(response: httpx.Response) -> AiApiError:
    try:
        data = response.json()
        description = str(data.get("error", {}).get("description") or data)
    except (ValueError, AttributeError, TypeError):
        description = (response.text or "")[:500]
    return AiApiError(response.status_code, description)


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    access_token: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"AI Server URL must include a scheme (http:// or https://), got {url!r}; "
            "without a scheme the request would resolve against the shared TrueConf "
            "Server base URL"
        )
    headers = kwargs.pop("headers", {})
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"
    logger.info("AI REQUEST %s %s", method, url)
    response = await client.request(method, url, headers=headers, **kwargs)
    logger.info("AI RESPONSE %s %s | status=%d", method, url, response.status_code)
    if response.is_error:
        raise _error(response)
    if response.status_code == 204:
        return {"status": "success"}
    return response.json()


async def auth_from_tcs(client: httpx.AsyncClient, sai_base: str, domain: str, token: str) -> AiTokenPair:
    """Exchange a TrueConf Server user token for an AI Server token pair."""
    data = await _request(
        client,
        "POST",
        f"{sai_base}{_V1}/auth/from-tcs",
        json={"domain": domain, "token": token},
    )
    return AiTokenPair.model_validate(data)


async def auth_refresh(client: httpx.AsyncClient, sai_base: str, refresh_token: str) -> AiTokenPair:
    """Refresh an AI Server token pair."""
    data = await _request(
        client,
        "POST",
        f"{sai_base}{_V1}/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    return AiTokenPair.model_validate(data)


async def list_transcriptions(
    client: httpx.AsyncClient,
    sai_base: str,
    access_token: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await _request(
        client,
        "GET",
        f"{sai_base}{_V1}/transcriptions",
        access_token=access_token,
        params=params,
    )


async def get_transcription(
    client: httpx.AsyncClient, sai_base: str, transcription_id: int, access_token: str
) -> dict[str, Any]:
    return await _request(
        client,
        "GET",
        f"{sai_base}{_V1}/transcriptions/{transcription_id}",
        access_token=access_token,
    )


async def get_transcription_lines(
    client: httpx.AsyncClient,
    sai_base: str,
    transcription_id: int,
    access_token: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await _request(
        client,
        "GET",
        f"{sai_base}{_V1}/transcriptions/{transcription_id}/lines",
        access_token=access_token,
        params=params,
    )


async def get_transcription_summary(
    client: httpx.AsyncClient, sai_base: str, transcription_id: int, access_token: str
) -> dict[str, Any]:
    return await _request(
        client,
        "GET",
        f"{sai_base}{_V1}/transcriptions/{transcription_id}/summary",
        access_token=access_token,
    )
