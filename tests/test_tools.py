"""Integration tests for conference tools (T11/T12/T13).

Mocks _request and get_access_token to verify what the tool sends to the API.
"""

from __future__ import annotations

from unittest.mock import patch
from fastmcp.server.auth import AccessToken

from app.mcp.tools.conferences.create_conference import create_conference
from app.mcp.tools.conferences.list_conferences import list_conferences
from app.mcp.tools.conferences.update_conference import update_conference


def _mock_access_token():
    return AccessToken(token="tc-test", client_id="user-1", scopes=[])


async def test_create_conference_normalizes_access_ru(
    mock_config_set,
) -> None:
    """create_conference(access='закрытая') sends 'private' in the body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

    with (
        patch(
            "app.mcp.tools.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.conferences.create_conference._request",
            side_effect=_capture,
        ),
    ):
        await create_conference(topic="Test", mode="лекция", access="закрытая")

    assert captured["json"]["access"] == "private"
    assert captured["json"]["mode"] == "OxP"


async def test_list_conferences_normalizes_mode(mock_config_set) -> None:
    """list_conferences(mode='лекция') sends 'OxP' in params."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["params"] = kwargs.get("params")
        return {"conferences": []}

    with patch(
        "app.mcp.tools.conferences.list_conferences._request",
        side_effect=_capture,
    ):
        await list_conferences(mode="лекция")

    assert captured["params"]["mode"] == "OxP"


async def test_create_conference_invalid_invitation_returns_error(
    mock_config_set,
) -> None:
    """create_conference with an invalid invitation (missing id) returns error dict."""
    with (
        patch(
            "app.mcp.tools.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.conferences.create_conference._request",
            return_value={"id": "conf-1"},
        ),
    ):
        result = await create_conference(
            topic="Test",
            mode="PxP",
            invitations=[{"display_name": "Alice"}],  # missing required "id"
        )
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "invalid_invitation"


async def test_create_conference_valid_invitations_passes(mock_config_set) -> None:
    """create_conference with valid invitations sends them in the body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

    with (
        patch(
            "app.mcp.tools.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.conferences.create_conference._request",
            side_effect=_capture,
        ),
    ):
        result = await create_conference(
            topic="Test",
            mode="PxP",
            invitations=[{"id": "u1", "display_name": "Alice", "is_moderator": True}],
        )
    assert "error" not in result
    inv_ids = [inv["id"] for inv in captured["json"]["invitations"]]
    assert "user-1" in inv_ids  # owner
    assert "u1" in inv_ids


async def test_update_conference_schedule_in_body(mock_config_set) -> None:
    """update_conference with schedule params sends schedule in PATCH body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference(
            "conf-1",
            schedule_type="once",
            schedule_start_time=1700000000,
            schedule_duration=3600,
        )

    assert captured["method"] == "PATCH"
    assert "schedule" in captured["json"]
    assert captured["json"]["schedule"]["type"] == "once"
    assert captured["json"]["schedule"]["start_time"] == 1700000000
    assert captured["json"]["schedule"]["duration"] == 3600


async def test_update_conference_no_schedule_excludes_it(mock_config_set) -> None:
    """update_conference without schedule params does not include schedule in body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference("conf-1", topic="New Topic")

    assert "schedule" not in captured["json"]
    assert captured["json"]["topic"] == "New Topic"


async def test_create_conference_no_owner_no_token_returns_auth_error(
    mock_config_set,
) -> None:
    """No owner + no token → consistent authorization_required error shape."""
    with (
        patch(
            "app.mcp.tools.conferences.create_conference.get_access_token",
            return_value=None,
        ),
        patch(
            "app.mcp.tools.conferences.create_conference._request",
            return_value={"id": "conf-1"},
        ),
    ):
        result = await create_conference(topic="Test", mode="PxP")
    assert result["error"] == "authorization_required"
    assert "login_url" in result
    assert "how_to" in result
    assert "message" in result
