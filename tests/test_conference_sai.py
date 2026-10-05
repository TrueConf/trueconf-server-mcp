"""Tests for conference transcription (sai) — models, build_sai, tools."""

from app._client_api._trueconf_server.models import ConferenceCreate, ConferenceSAI
from app.mcp.tools.trueconf_server.conferences.create_conference import create_conference
from app.mcp.tools.trueconf_server.conferences.sai_utils import build_sai
from app.mcp.tools.trueconf_server.conferences.update_conference import update_conference


def _mock_access_token():
    from fastmcp.server.auth import AccessToken

    return AccessToken(token="tc-test", client_id="user-1", scopes=[])


# ── models ──────────────────────────────────────────────────────────────


def test_conference_create_dumps_sai_block():
    conf = ConferenceCreate(
        topic="T",
        owner="user-1",
        mode="PxP",
        sai=ConferenceSAI(recording_enabled=True, recognition_language="ru"),
    )
    body = conf.model_dump(exclude_none=True)
    assert body["sai"] == {"recording_enabled": True, "recognition_language": "ru"}


def test_conference_create_omits_sai_when_unset():
    conf = ConferenceCreate(topic="T", owner="user-1", mode="PxP")
    assert "sai" not in conf.model_dump(exclude_none=True)


# ── build_sai ───────────────────────────────────────────────────────────


def test_build_sai_all_none_returns_none():
    assert build_sai(None, None, None) is None


def test_build_sai_subset_keeps_only_given():
    sai = build_sai(True, None, None)
    assert sai is not None
    assert sai.model_dump(exclude_none=True) == {"recording_enabled": True}


def test_build_sai_full():
    sai = build_sai(True, "ru", True)
    assert sai.model_dump(exclude_none=True) == {
        "recording_enabled": True,
        "recognition_language": "ru",
        "auto_recognition_enabled": True,
    }


# ── create_conference tool ──────────────────────────────────────────────


async def test_create_conference_sends_sai_block(mock_config_set):
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

    from unittest.mock import patch

    with (
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference._request",
            side_effect=_capture,
        ),
    ):
        await create_conference(
            conference_name="Test",
            mode="PxP",
            transcription_enabled=True,
            transcription_language="ru",
        )

    assert captured["json"]["sai"] == {
        "recording_enabled": True,
        "recognition_language": "ru",
    }


async def test_create_conference_without_sai_params_omits_field(mock_config_set):
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

    from unittest.mock import patch

    with (
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference._request",
            side_effect=_capture,
        ),
    ):
        await create_conference(conference_name="Test", mode="PxP")

    assert "sai" not in captured["json"]


# ── update_conference tool ──────────────────────────────────────────────


async def test_update_conference_sends_sai_block(mock_config_set):
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

    from unittest.mock import patch

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference(
            conference_id="conf-1",
            transcription_enabled=False,
            transcription_auto_detect_language=True,
        )

    assert captured["json"]["sai"] == {
        "recording_enabled": False,
        "auto_recognition_enabled": True,
    }


async def test_update_conference_without_sai_params_omits_field(mock_config_set):
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

    from unittest.mock import patch

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference(conference_id="conf-1", conference_name="New")

    assert "sai" not in captured["json"]
