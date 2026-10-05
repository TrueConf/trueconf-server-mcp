"""Tests for app._client_api._trueconf_server_ai.client via httpx.MockTransport."""

import json

import httpx
import pytest

from app._client_api._trueconf_server_ai.client import (
    AiApiError,
    auth_from_tcs,
    get_transcription,
    get_transcription_lines,
    get_transcription_summary,
    list_transcriptions,
)

SAI = "https://sai.example"


def _transport_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_auth_from_tcs_sends_domain_and_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access_token": "ai-a", "refresh_token": "ai-r"})

    pair = await auth_from_tcs(_transport_client(handler), SAI, "10.0.0.1", "tc-token")
    assert captured["url"].startswith(f"{SAI}/api/user/v1/auth/from-tcs")
    assert captured["body"] == {"domain": "10.0.0.1", "token": "tc-token"}
    assert pair.access_token == "ai-a"
    assert pair.refresh_token == "ai-r"


async def test_auth_from_tcs_error_raises_ai_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": {
                    "code": 500,
                    "description": "provider (full) with host X not found",
                }
            },
        )

    with pytest.raises(AiApiError) as exc_info:
        await auth_from_tcs(_transport_client(handler), SAI, "X", "tok")
    assert exc_info.value.status_code == 500
    assert "not found" in exc_info.value.description


async def test_auth_from_tcs_scheme_less_base_raises_before_network():
    """Scheme-less sai_base must fail loudly instead of resolving against base_url.

    Regression guard: a URL without http(s):// is relative, so httpx would
    resolve it against the shared client's base_url (the TrueConf Server),
    silently producing `https://<TCS>/api/v4/sai01t.trueconf.name/...` → 404.
    """

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover — must never be reached
        raise AssertionError("network must not be reached")

    with pytest.raises(ValueError, match="scheme"):
        await auth_from_tcs(_transport_client(handler), "sai01t.trueconf.name", "X", "tok")


async def test_list_transcriptions_sends_bearer_and_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"transcriptions": [], "page": {}})

    resp = await list_transcriptions(_transport_client(handler), SAI, "ai-a", params={"page": 2})
    assert captured["auth"] == "Bearer ai-a"
    assert "page=2" in captured["url"]
    assert resp == {"transcriptions": [], "page": {}}


async def test_get_transcription_and_lines_and_summary():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/transcriptions/2"):
            return httpx.Response(200, json={"id": 2})
        if request.url.path.endswith("/lines"):
            return httpx.Response(200, json={"lines": []})
        if request.url.path.endswith("/summary"):
            return httpx.Response(200, json={"summaries": []})
        return httpx.Response(404)

    client = _transport_client(handler)
    assert (await get_transcription(client, SAI, 2, "ai-a")) == {"id": 2}
    assert (await get_transcription_lines(client, SAI, 2, "ai-a", params={})) == {"lines": []}
    assert (await get_transcription_summary(client, SAI, 2, "ai-a")) == {"summaries": []}
    assert any(u.endswith("/api/user/v1/transcriptions/2/lines") for u in seen)
