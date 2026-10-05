"""Integration tests for conference tools (T11/T12/T13).

Mocks _request and get_access_token to verify what the tool sends to the API.
Scheduled-conference tests use absolute ISO dates so results are deterministic
regardless of the server's current date.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastmcp.server.auth import AccessToken

from app.mcp.tools.trueconf_server.conferences.add_invitation import add_invitation
from app.mcp.tools.trueconf_server.conferences.create_conference import create_conference
from app.mcp.tools.trueconf_server.conferences.list_conferences import list_conferences
from app.mcp.tools.trueconf_server.conferences.update_conference import update_conference
from app.mcp.tools.trueconf_server.conferences.update_invitation import update_invitation
from app.mcp.tools.trueconf_server.users.get_user_addressbook import get_user_addressbook


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
            "app.mcp.tools.trueconf_server.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference._request",
            side_effect=_capture,
        ),
    ):
        await create_conference(conference_name="Test", mode="лекция", access="закрытая")

    assert captured["json"]["access"] == "private"
    assert captured["json"]["mode"] == "OxP"


async def test_list_conferences_normalizes_mode(mock_config_set) -> None:
    """list_conferences(mode='лекция') sends 'OxP' in params."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["params"] = kwargs.get("params")
        return {"conferences": []}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.list_conferences._request",
        side_effect=_capture,
    ):
        await list_conferences(mode="лекция")

    assert captured["params"]["mode"] == "OxP"


async def test_list_conferences_invalid_mode_returns_error(
    mock_config_set,
) -> None:
    """list_conferences with an unresolvable mode returns invalid_mode, not a
    raw ValueError traceback (same contract as create/update)."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"conferences": []}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.list_conferences._request",
        side_effect=_capture,
    ):
        result = await list_conferences(mode="bogus-mode")

    assert result["error"] == "invalid_mode"
    assert captured == []  # no upstream request was made


async def test_list_conferences_normalizes_access(mock_config_set) -> None:
    """list_conferences(access='открытая') sends 'public' in params.

    Regression: the access filter was passed through raw, so a Russian value
    like 'открытая' went to the API as-is and silently returned an empty list.
    """
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["params"] = kwargs.get("params")
        return {"conferences": []}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.list_conferences._request",
        side_effect=_capture,
    ):
        await list_conferences(access="открытая")

    assert captured["params"]["access"] == "public"


async def test_list_conferences_invalid_access_returns_error(
    mock_config_set,
) -> None:
    """list_conferences with an unresolvable access returns invalid_access,
    not a raw pydantic pass-through (same contract as mode)."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"conferences": []}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.list_conferences._request",
        side_effect=_capture,
    ):
        result = await list_conferences(access="bogus-access")

    assert result["error"] == "invalid_access"
    assert captured == []  # no upstream request was made


async def test_create_conference_invalid_invitation_returns_error(
    mock_config_set,
) -> None:
    """create_conference with an invalid invitation (missing id) returns a
    human-readable instruction instead of raw pydantic errors."""
    with (
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference._request",
            return_value={"id": "conf-1"},
        ),
    ):
        result = await create_conference(
            conference_name="Test",
            mode="PxP",
            invitations=[{"display_name": "Alice"}],  # missing required "id"
        )
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "invalid_invitation"
    assert "id" in result.get("message", "")
    assert "кавычек" in result.get("message", "") or "quotes" in result.get("message", "")
    # raw pydantic errors must NOT leak into the message
    assert "pydantic" not in result.get("message", "").lower()
    assert "Field required" not in result.get("message", "")


async def test_create_conference_invalid_invitation_other_error_keeps_detail(
    mock_config_set,
) -> None:
    """Non-missing-id pydantic errors still include the raw validation detail."""
    with (
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference._request",
            return_value={"id": "conf-1"},
        ),
    ):
        result = await create_conference(
            conference_name="Test",
            mode="PxP",
            invitations=[{"id": "u1", "is_moderator": "not-a-bool"}],  # wrong type, not missing id
        )
    assert isinstance(result, dict)
    assert result["error"] == "invalid_invitation"
    assert "detail" in result  # raw pydantic preserved
    assert "id" not in result.get("message", "").lower()  # no quotes hint here


async def test_create_conference_valid_invitations_passes(mock_config_set) -> None:
    """create_conference with valid invitations sends them in the body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Test",
            mode="PxP",
            invitations=[{"id": "u1", "display_name": "Alice", "is_moderator": True}],
        )
    assert "error" not in result
    inv_ids = [inv["id"] for inv in captured["json"]["invitations"]]
    assert "user-1" in inv_ids  # owner
    assert "u1" in inv_ids


async def test_create_conference_maps_name_to_topic(mock_config_set) -> None:
    """conference_name is sent to the API as topic."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        await create_conference(conference_name="Встреча", mode="PxP")

    assert captured["json"]["topic"] == "Встреча"


async def test_create_conference_no_owner_no_token_returns_auth_error(
    mock_config_set,
) -> None:
    """No owner + no token → consistent authorization_required error shape."""
    with (
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference.get_access_token",
            return_value=None,
        ),
        patch(
            "app.mcp.tools.trueconf_server.conferences.create_conference._request",
            return_value={"id": "conf-1"},
        ),
    ):
        result = await create_conference(conference_name="Test", mode="PxP")
    assert result["error"] == "authorization_required"
    assert "login_url" in result
    assert "how_to" in result
    assert "message" in result


# ── Scheduled conferences: date / time / timezone ──────────────────────


async def test_create_conference_once_schedule_sends_start_time(
    mock_config_set,
) -> None:
    """once + ISO date + timezone → schedule carries converted UTC start_time."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
            conference_name="Once",
            mode="PxP",
            schedule_type="once",
            schedule_date="2026-08-17",
            schedule_time="13:00",
            schedule_duration=3600,
            timezone="+3",
        )

    schedule = captured["json"]["schedule"]
    assert schedule["type"] == "once"
    # 2026-08-17 13:00 MSK (+3) = 2026-08-17 10:00 UTC
    assert schedule["start_time"] == int(datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc).timestamp())
    assert schedule["time"] == "10:00"
    assert schedule["duration"] == 3600
    assert schedule["special_time_offset"] == 180


async def test_create_conference_once_iana_timezone_resolves_offset(
    mock_config_set,
) -> None:
    """IANA name Europe/Moscow → 180 regardless of host tz."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
            conference_name="Once IANA",
            mode="PxP",
            schedule_type="once",
            schedule_duration=3600,
            schedule_date="2026-08-17",
            schedule_time="10:00",
            timezone="Europe/Moscow",
        )

    schedule = captured["json"]["schedule"]
    assert schedule["special_time_offset"] == 180
    assert schedule["time"] == "07:00"


async def test_create_conference_week_schedule_sends_days_and_time(
    mock_config_set,
) -> None:
    """week + timezone → schedule carries days, converted UTC time, offset."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
            conference_name="Weekly",
            mode="PxP",
            schedule_type="week",
            schedule_date="2026-08-17",
            schedule_days=["monday", "wednesday"],
            schedule_time="13:00",
            schedule_duration=3600,
            timezone="+3",
        )

    schedule = captured["json"]["schedule"]
    assert schedule["type"] == "week"
    assert schedule["days"] == ["monday", "wednesday"]
    assert schedule["time"] == "10:00"
    assert schedule["duration"] == 3600
    assert schedule["special_time_offset"] == 180


async def test_create_conference_scheduled_without_timezone_returns_error(
    mock_config_set,
) -> None:
    """once without timezone → invalid_schedule, no host-offset guessing."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Once no tz",
            mode="PxP",
            schedule_type="once",
            schedule_duration=3600,
            schedule_date="2026-08-17",
            schedule_time="13:00",
        )

    assert result["error"] == "invalid_schedule"
    assert "timezone" in result["message"]
    assert captured == []


async def test_create_conference_invalid_timezone_returns_error(
    mock_config_set,
) -> None:
    """Unknown timezone → clean error dict, no API call."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Bad tz",
            mode="PxP",
            schedule_type="once",
            schedule_duration=3600,
            schedule_date="2026-08-17",
            schedule_time="13:00",
            timezone="Mars/Olympus",
        )

    assert result["error"] == "invalid_timezone"
    assert "Mars/Olympus" in result["message"]
    assert captured == []  # no upstream request was made


async def test_update_conference_schedule_with_timezone_sends_offset(
    mock_config_set,
) -> None:
    """update + schedule + timezone → PATCH body carries converted start_time."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference(
            "conf-1",
            schedule_type="once",
            schedule_date="2026-08-17",
            schedule_time="13:00",
            schedule_duration=3600,
            timezone="+3",
        )

    assert captured["method"] == "PATCH"
    schedule = captured["json"]["schedule"]
    assert schedule["type"] == "once"
    assert schedule["start_time"] == int(datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc).timestamp())
    assert schedule["special_time_offset"] == 180


async def test_update_conference_schedule_without_timezone_returns_error(
    mock_config_set,
) -> None:
    """update + schedule but no timezone → one GET to try inheriting the
    offset; nothing to inherit (no current schedule) → clean error, no PATCH."""
    methods: list = []

    async def _capture(method, path, **kwargs):
        methods.append(method)
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference(
            "conf-1",
            schedule_type="once",
            schedule_date="2026-08-17",
            schedule_time="13:00",
            schedule_duration=3600,
        )

    assert result["error"] == "invalid_schedule"
    assert "timezone" in result["message"]
    assert methods == ["GET"]  # inheritance attempt, no PATCH


async def test_create_conference_invalid_schedule_days_returns_error(
    mock_config_set,
) -> None:
    """Invalid weekday value → clean error dict, not a traceback."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Bad days",
            mode="PxP",
            schedule_type="week",
            schedule_date="2026-08-17",
            schedule_days=["funday"],
            schedule_time="13:00",
            timezone="+3",
        )

    assert result["error"] == "invalid_schedule"
    assert captured == []  # no upstream request was made


async def test_update_conference_days_without_type_returns_error(
    mock_config_set,
) -> None:
    """days/time without schedule_type → error (must not clobber to none)."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference(
            "conf-1",
            schedule_days=["monday"],
            schedule_time="13:00",
        )

    assert result["error"] == "invalid_schedule"
    assert captured == []  # no upstream request was made


async def test_create_conference_uses_relative_weekday_phrase(mock_config_set):
    """Once with a relative date phrase builds a schedule successfully."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Next",
            mode="PxP",
            schedule_type="once",
            schedule_duration=3600,
            schedule_date="next Monday at 13:00",
            timezone="+3",
        )

    assert "error" not in result
    assert captured["json"]["schedule"]["type"] == "once"
    assert captured["json"]["schedule"]["special_time_offset"] == 180


async def test_create_conference_once_without_date_returns_error(
    mock_config_set,
) -> None:
    """once without schedule_date → clean invalid_schedule, no API call."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Once no date",
            mode="PxP",
            schedule_type="once",
            schedule_time="13:00",
            timezone="+3",
        )

    assert result["error"] == "invalid_schedule"
    assert captured == []


async def test_create_conference_once_without_time_returns_error(
    mock_config_set,
) -> None:
    """once without schedule_time and without embedded time → error."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Once no time",
            mode="PxP",
            schedule_type="once",
            schedule_date="2026-08-17",
            timezone="+3",
        )

    assert result["error"] == "invalid_schedule"
    assert captured == []


async def test_update_conference_maps_name_to_topic(mock_config_set) -> None:
    """conference_name is sent to the API as topic on update."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference("conf-1", conference_name="New Topic")

    assert captured["json"]["topic"] == "New Topic"


async def test_update_conference_no_schedule_excludes_it(mock_config_set) -> None:
    """update_conference without schedule params does not include schedule in body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        await update_conference("conf-1", conference_name="New Topic")

    assert "schedule" not in captured["json"]
    assert captured["json"]["topic"] == "New Topic"


async def test_update_conference_schedule_type_none_clears_schedule(
    mock_config_set,
) -> None:
    """Explicit schedule_type='none' sends schedule {"type": "none"} so a
    previously scheduled conference becomes unscheduled (the documented
    PATCH way to clear the schedule)."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", schedule_type="none")

    assert "error" not in result
    assert captured["json"]["schedule"] == {"type": "none"}


async def test_update_conference_schedule_type_none_with_fields_returns_error(
    mock_config_set,
) -> None:
    """schedule_type='none' combined with schedule fields is contradictory →
    clean invalid_schedule, no API call."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference(
            "conf-1",
            schedule_type="none",
            schedule_date="2026-08-17",
        )

    assert result["error"] == "invalid_schedule"
    assert captured == []  # no upstream request was made


# ── Address book ───────────────────────────────────────────────────────


async def test_get_user_addressbook_builds_path_and_params(mock_config_set) -> None:
    """Single-word search maps to filter_search/page_id in path users/<client_id>/addressbook."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        captured["version"] = kwargs.get("version")
        return {"contacts": [], "next_page_id": None}

    with (
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook._request",
            side_effect=_capture,
        ),
    ):
        await get_user_addressbook(search="Иван", page=2, page_size=25)

    assert captured["method"] == "GET"
    assert captured["path"] == "users/user-1/addressbook"
    assert captured["version"] == "v4.1"
    assert captured["params"] == {
        "filter_search": "Иван",
        "page_id": 2,
        "page_size": 25,
    }


async def test_get_user_addressbook_omits_none_params(mock_config_set) -> None:
    """No filters → no query params sent."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["params"] = kwargs.get("params")
        captured["version"] = kwargs.get("version")
        return {"contacts": []}

    with (
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook._request",
            side_effect=_capture,
        ),
    ):
        await get_user_addressbook()

    assert captured["params"] == {}
    assert captured["version"] == "v4.1"


async def test_get_user_addressbook_no_token_returns_auth_error(
    mock_config_set,
) -> None:
    """No token → authorization_required, no upstream request."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"contacts": []}

    with (
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook.get_access_token",
            return_value=None,
        ),
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook._request",
            side_effect=_capture,
        ),
    ):
        result = await get_user_addressbook()

    assert result["error"] == "authorization_required"
    assert captured == []


async def test_get_user_addressbook_single_word_still_works(mock_config_set) -> None:
    """Single-word search keeps one filter_search request (regression)."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs.get("params"))
        return {
            "contacts": [{"id": "elisa", "display_name": "Алиса Лесова"}],
            "next_page_id": -1,
        }

    with (
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook._request",
            side_effect=_capture,
        ),
    ):
        await get_user_addressbook(search="  Алиса  ")

    # single call, params stripped, no page_id
    assert len(captured) == 1
    assert captured[0] == {"filter_search": "Алиса"}


async def test_get_user_addressbook_multiword_intersects(mock_config_set) -> None:
    """Multi-word search makes one request per word and intersects by id."""
    by_word: dict = {
        "Алиса": {
            "contacts": [
                {"id": "elisa", "display_name": "Алиса Лесова"},
                {"id": "alina", "display_name": "Алиса Романова"},
            ],
            "next_page_id": -1,
        },
        "Лесова": {
            "contacts": [
                {"id": "elisa", "display_name": "Алиса Лесова"},
            ],
            "next_page_id": -1,
        },
    }

    async def _capture(method, path, **kwargs):
        params = kwargs.get("params")
        word = params.get("filter_search")
        return by_word[word]

    with (
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook._request",
            side_effect=_capture,
        ),
    ):
        result = await get_user_addressbook(search="Алиса Лесова")

    assert result == {
        "contacts": [{"id": "elisa", "display_name": "Алиса Лесова", "user_id": "elisa"}],
        "next_page_id": -1,
    }
    assert list(by_word.keys()) == ["Алиса", "Лесова"]


async def test_get_user_addressbook_multiword_paginates(mock_config_set) -> None:
    """Multi-word search follows next_page_id until exhausted."""
    call_params: list = []
    versions: list = []

    async def _capture(method, path, **kwargs):
        params = kwargs.get("params")
        call_params.append(params)
        versions.append(kwargs.get("version"))
        page = params.get("page_id")
        if page == 2:
            return {"contacts": [{"id": "elisa"}], "next_page_id": -1}
        return {"contacts": [{"id": "x"}], "next_page_id": 2}

    with (
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook.get_access_token",
            return_value=_mock_access_token(),
        ),
        patch(
            "app.mcp.tools.trueconf_server.users.get_user_addressbook._request",
            side_effect=_capture,
        ),
    ):
        result = await get_user_addressbook(search="Одно Слово")

    ids = {c["id"] for c in result["contacts"]}
    assert ids == {"x", "elisa"}
    # per-word pagination: page_id passed for the second page
    assert call_params[1]["page_id"] == 2
    # every per-word request goes to the v4.1 addressbook endpoint
    assert versions
    assert all(v == "v4.1" for v in versions)


# ── Guest rights ───────────────────────────────────────────────────────


async def test_create_conference_guest_rights_requires_public(mock_config_set) -> None:
    """guest_rights without access='public' → clean error, no API call."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Test",
            mode="PxP",
            access="private",
            guest_rights=["video_send"],
        )

    assert result["error"] == "guest_rights_requires_public_access"
    assert captured == []


async def test_create_conference_guest_rights_with_public_sends_rights(
    mock_config_set,
) -> None:
    """guest_rights with access='public' → rights.guest in body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Test",
            mode="PxP",
            access="public",
            guest_rights=["video_send"],
        )

    assert "error" not in result
    assert captured["json"]["rights"] == {"guest": {"video_send": False}}


# ── Registration ───────────────────────────────────────────────────────


async def test_create_conference_registration_enabled_sends_registration(
    mock_config_set,
) -> None:
    """registration_enabled=True → registration {enabled: true} in body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Webinar",
            mode="PxP",
            registration_enabled=True,
        )

    assert "error" not in result
    assert captured["json"]["registration"] == {"enabled": True}


async def test_create_conference_registration_with_window_and_limit(
    mock_config_set,
) -> None:
    """Window + limit → full registration block, limit flag derived."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Webinar",
            mode="PxP",
            registration_enabled=True,
            registration_start_at=1000,
            registration_end_at=2000,
            registration_participants_limit=10,
        )

    assert "error" not in result
    assert captured["json"]["registration"] == {
        "enabled": True,
        "start_at": 1000,
        "end_at": 2000,
        "participants_limit": 10,
        "participants_limit_enabled": True,
    }


async def test_create_conference_registration_fields_without_enabled_error(
    mock_config_set,
) -> None:
    """registration_start_at without registration_enabled → error, no API call."""
    captured: list = []

    async def _capture(method, path, **kwargs):
        captured.append(kwargs)
        return {"id": "conf-1"}

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
        result = await create_conference(
            conference_name="Webinar",
            mode="PxP",
            registration_start_at=1000,
        )

    assert result["error"] == "invalid_registration"
    assert "registration_enabled" in result["message"]
    assert captured == []


async def test_create_conference_without_registration_omits_field(
    mock_config_set,
) -> None:
    """No registration params → no registration key in the body."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"id": "conf-1"}

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
        await create_conference(conference_name="Plain", mode="PxP")

    assert "registration" not in captured["json"]


# ── Invitations ────────────────────────────────────────────────────────


async def test_add_invitation_sends_no_is_moderator(mock_config_set) -> None:
    """add_invitation never sends is_moderator (server drops it)."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.add_invitation._request",
        side_effect=_capture,
    ):
        await add_invitation("conf-1", "u2", display_name="Bob")

    assert captured["json"] == {"invitation": {"id": "u2", "display_name": "Bob"}}
    assert "is_moderator" not in captured["json"]["invitation"]


async def test_update_conference_guest_display_name_maps_403(
    mock_config_set,
) -> None:
    """403 from PATCH → guest_display_name_only hint (registered user likely)."""
    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_invitation._request",
        return_value={
            "error": "HTTP 403",
            "status_code": 403,
            "detail": "Forbidden",
        },
    ):
        result = await update_invitation("conf-1", "inv-1", "New Guest Name")

    assert result["error"] == "guest_display_name_only"
    assert result["status_code"] == 403
    assert "registered user" in result["message"]
    assert "how_to" in result


async def test_update_conference_guest_display_name_passthrough_success(
    mock_config_set,
) -> None:
    """Successful PATCH passes the server response through unchanged."""
    captured: dict = {}

    async def _capture(method, path, **kwargs):
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"invitation": {"id": "inv-1", "display_name": "New Guest Name"}}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_invitation._request",
        side_effect=_capture,
    ):
        result = await update_invitation("conf-1", "inv-1", "New Guest Name")

    assert captured["path"] == "conferences/conf-1/invitations/inv-1"
    assert captured["json"] == {"invitation": {"display_name": "New Guest Name"}}
    assert result["invitation"]["display_name"] == "New Guest Name"


# ── Partial updates: current state fills the gaps ───────────────────────


async def test_update_conference_guest_rights_without_access_public_conf(
    mock_config_set,
) -> None:
    """guest_rights without access on an already-public conference → PATCH
    with rights only: current access is checked via GET, so the LLM does
    not have to re-send access='public'."""
    captured: dict = {}
    current = {"id": "conf-1", "access": "public", "schedule": {"type": "none"}}

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", guest_rights=["video_send"])

    assert "error" not in result
    assert captured["method"] == "PATCH"
    assert captured["json"]["rights"] == {"guest": {"video_send": False}}
    assert "access" not in captured["json"]
    assert "schedule" not in captured["json"]


async def test_update_conference_guest_rights_without_access_private_conf(
    mock_config_set,
) -> None:
    """guest_rights without access on a private conference → still a clean
    error (rights have nothing to apply to), no PATCH."""
    calls: list = []
    current = {"id": "conf-1", "access": "private", "schedule": {"type": "none"}}

    async def _capture(method, path, **kwargs):
        calls.append(method)
        if method == "GET":
            return current
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", guest_rights=["video_send"])

    assert result["error"] == "guest_rights_requires_public_access"
    assert calls == ["GET"]  # no PATCH was sent


# Current server-side state as returned by GET /conferences/{id}
# (conference.ScheduleOutput: start_time/end_time are strings, no ``time``).
CURRENT_ONCE = {
    "type": "once",
    "start_time": "2026-08-17T10:00:00Z",
    "end_time": "2026-08-17T11:00:00Z",
    "duration": 3600,
    "special_time_offset": 180,
}
CURRENT_WEEK = {
    "type": "week",
    "start_time": "2026-08-17T10:00:00Z",
    "end_time": "2026-08-17T11:00:00Z",
    "duration": 3600,
    "days": ["monday", "wednesday"],
    "special_time_offset": 180,
}


async def test_update_conference_partial_schedule_time_only_inherits_rest(
    mock_config_set,
) -> None:
    """Changing only schedule_time inherits duration/offset/date from the
    current schedule — one PATCH, no get_conference needed by the LLM."""
    captured: dict = {}
    current = {"id": "conf-1", "access": "private", "schedule": CURRENT_ONCE}

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", schedule_type="once", schedule_time="14:00")

    assert "error" not in result
    assert captured["method"] == "PATCH"
    schedule = captured["json"]["schedule"]
    assert schedule["type"] == "once"
    # 14:00 at the inherited +3 offset = 11:00 UTC, same date
    assert schedule["time"] == "11:00"
    assert schedule["duration"] == 3600
    assert schedule["special_time_offset"] == 180
    assert schedule["start_time"] == int(datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc).timestamp())


async def test_update_conference_partial_schedule_api_envelope_inherits_rest(
    mock_config_set,
) -> None:
    """The real API wraps GET /conferences/{id} in {"conference": {...}};
    inheritance must read the unwrapped object (regression: partial update
    failed with 'schedule_date is required' against the live server)."""
    captured: dict = {}
    current = {
        "conference": {
            "id": "conf-1",
            "access": "public",
            "schedule": CURRENT_ONCE,
        }
    }

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", schedule_type="once", schedule_time="14:00")

    assert "error" not in result
    assert captured["method"] == "PATCH"
    schedule = captured["json"]["schedule"]
    assert schedule["time"] == "11:00"
    assert schedule["duration"] == 3600
    assert schedule["special_time_offset"] == 180


async def test_update_conference_guest_rights_api_envelope_public_ok(
    mock_config_set,
) -> None:
    """guest_rights without access on a public conference must not be
    rejected as 'unknown' access when the API returns the envelope shape."""
    captured: dict = {}
    current = {
        "conference": {
            "id": "conf-1",
            "access": "public",
            "schedule": {"type": "none"},
        }
    }

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", guest_rights=["recording"])

    assert "error" not in result
    assert captured["method"] == "PATCH"
    assert captured["json"]["rights"] == {
        "guest": {
            "recording": False,
        }
    }


async def test_update_conference_partial_schedule_duration_only_keeps_time(
    mock_config_set,
) -> None:
    """Changing only schedule_duration keeps the current time/date/offset."""
    captured: dict = {}
    current = {"id": "conf-1", "access": "private", "schedule": CURRENT_ONCE}

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", schedule_type="once", schedule_duration=7200)

    assert "error" not in result
    schedule = captured["json"]["schedule"]
    assert schedule["time"] == "10:00"
    assert schedule["duration"] == 7200
    assert schedule["special_time_offset"] == 180
    assert schedule["start_time"] == int(datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc).timestamp())


async def test_update_conference_partial_schedule_week_time_only_keeps_days(
    mock_config_set,
) -> None:
    """week + new time only → days/duration/first-occurrence date inherited."""
    captured: dict = {}
    current = {"id": "conf-1", "access": "private", "schedule": CURRENT_WEEK}

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", schedule_type="week", schedule_time="15:00")

    assert "error" not in result
    schedule = captured["json"]["schedule"]
    assert schedule["type"] == "week"
    assert schedule["days"] == ["monday", "wednesday"]
    assert schedule["time"] == "12:00"
    assert schedule["duration"] == 3600
    assert schedule["special_time_offset"] == 180
    assert schedule["start_time"] == int(datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc).timestamp())


async def test_update_conference_partial_schedule_timezone_only_inherited(
    mock_config_set,
) -> None:
    """date+time+duration without timezone → offset inherited from the
    current schedule (consistent with any other single missing field)."""
    captured: dict = {}
    current = {"id": "conf-1", "access": "private", "schedule": CURRENT_ONCE}

    async def _capture(method, path, **kwargs):
        if method == "GET":
            return current
        captured["method"] = method
        captured["json"] = kwargs.get("json")
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference(
            "conf-1",
            schedule_type="once",
            schedule_date="2026-08-17",
            schedule_time="13:00",
            schedule_duration=3600,
        )

    assert "error" not in result
    schedule = captured["json"]["schedule"]
    assert schedule["special_time_offset"] == 180
    assert schedule["time"] == "10:00"
    assert schedule["duration"] == 3600
    assert schedule["start_time"] == int(datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc).timestamp())


async def test_update_conference_full_schedule_no_get(mock_config_set) -> None:
    """Complete schedule input never fetches the current conference."""
    calls: list = []

    async def _capture(method, path, **kwargs):
        calls.append(method)
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference(
            "conf-1",
            schedule_type="once",
            schedule_date="2026-08-17",
            schedule_time="13:00",
            schedule_duration=3600,
            timezone="+3",
        )

    assert "error" not in result
    assert calls == ["PATCH"]  # no extra GET on the complete path


async def test_update_conference_partial_schedule_without_existing_schedule_errors(
    mock_config_set,
) -> None:
    """Partial schedule on an unscheduled conference → the usual
    required-field error (nothing to inherit from), no PATCH."""
    calls: list = []
    current = {"id": "conf-1", "access": "private", "schedule": {"type": "none"}}

    async def _capture(method, path, **kwargs):
        calls.append(method)
        if method == "GET":
            return current
        return {"status": "success"}

    with patch(
        "app.mcp.tools.trueconf_server.conferences.update_conference._request",
        side_effect=_capture,
    ):
        result = await update_conference("conf-1", schedule_type="once", schedule_time="14:00")

    assert result["error"] == "invalid_schedule"
    assert "PATCH" not in calls
