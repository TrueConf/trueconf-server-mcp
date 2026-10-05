"""Tests for API response / output models in TrueConf Server and AI Server."""

from app._client_api._trueconf_server.models import (
    ActionSuccessOutput,
    AddressBookOutput,
    CalculateConferencesOutput,
    CalendarsOutput,
    ConferenceListOutput,
    ConferenceMeOutput,
    ConferenceOutput,
    ConferenceOwnerOutput,
    DeeplinksOutput,
    InvitationListOutput,
    InvitationOutput,
    ParticipantListOutput,
    RecordingListOutput,
    RecordingOutput,
    RegistrationOutput,
    SharedLinksOutput,
    TranslationsOutput,
)
from app._client_api._trueconf_server_ai.models import (
    TranscriptionLinesOutput,
    TranscriptionListOutput,
    TranscriptionOutput,
    TranscriptionSummaryOutput,
)


def test_conference_output_unwraps_envelope_and_renames_fields():
    raw_api_response = {
        "conference": {
            "id": "conf-42",
            "topic": "Weekly Standup",
            "owner": "john",
            "state": "running",
            "mode": "PxP",
            "access": "public",
            "schedule": {
                "type": "week",
                "duration": 3600,
                "days": ["monday", "friday"],
                "start_time": "1720000000",
                "special_time_offset": 180,
            },
            "sai": {
                "recording_enabled": True,
                "recognition_language": "ru",
                "auto_recognition_enabled": True,
            },
            "extra_internal_field_to_ignore": "ignored_value",
        }
    }
    model = ConferenceOutput.model_validate(raw_api_response)
    data = model.model_dump(exclude_none=True)

    assert data["conference_id"] == "conf-42"
    assert data["conference_name"] == "Weekly Standup"
    assert data["owner"] == "john"
    assert data["status"] == "running"
    assert data["conference_mode"] == "PxP"
    assert data["mode"] == "all on screen"
    assert data["schedule_type"] == "week"
    assert data["schedule_duration"] == 3600
    assert data["schedule_days"] == ["monday", "friday"]
    assert data["schedule_start_time"] == "1720000000"
    assert data["schedule_time_offset"] == 180
    assert data["transcription_enabled"] is True
    assert data["transcription_language"] == "ru"
    assert data["transcription_auto_detect"] is True
    # Extra field is ignored
    assert "extra_internal_field_to_ignore" not in data
    # Computed aliases for backward compat
    assert data["id"] == "conf-42"
    assert data["topic"] == "Weekly Standup"


def test_short_conference_output_and_list():
    raw_list = {
        "results": 1,
        "conferences": [
            {
                "id": "c1",
                "topic": "Quick Sync",
                "owner": "alice",
                "state": "stopped",
                "mode": "OxP",
                "schedule": {"type": "none"},
            }
        ],
    }
    output = ConferenceListOutput.model_validate(raw_list)
    dumped = output.model_dump(exclude_none=True)

    assert dumped["total"] == 1
    assert len(dumped["conferences"]) == 1
    c = dumped["conferences"][0]
    assert c["conference_id"] == "c1"
    assert c["conference_name"] == "Quick Sync"
    assert c["status"] == "stopped"
    assert c["conference_mode"] == "OxP"
    assert c["mode"] == "video lecture"
    assert c["id"] == "c1"
    assert c["topic"] == "Quick Sync"


def test_invitation_output_and_list():
    raw = {"invitation": {"id": "user-1", "display_name": "Bob Guest", "is_moderator": True}}
    inv = InvitationOutput.model_validate(raw).model_dump(exclude_none=True)
    assert inv["invitation_id"] == "user-1"
    assert inv["display_name"] == "Bob Guest"
    assert inv["is_moderator"] is True
    assert inv["id"] == "user-1"

    raw_list = {"invitations": [{"id": "u1", "display_name": "Guest 1"}]}
    inv_list = InvitationListOutput.model_validate(raw_list).model_dump(exclude_none=True)
    assert len(inv_list["invitations"]) == 1
    assert inv_list["invitations"][0]["invitation_id"] == "u1"


def test_participant_output_and_list():
    raw = {
        "cnt": 1,
        "list": [
            {
                "id": "conn-123",
                "display_name": "Speaker 1",
                "flag": 2,
                "duration": 500,
                "app_id": "desktop",
            }
        ],
    }
    res = ParticipantListOutput.model_validate(raw).model_dump(exclude_none=True)
    assert res["total"] == 1
    p = res["participants"][0]
    assert p["participant_id"] == "conn-123"
    assert p["display_name"] == "Speaker 1"
    assert p["role"] == 2
    assert p["duration"] == 500
    assert p["id"] == "conn-123"


def test_conference_owner_and_me():
    raw_owner = {
        "owner": {
            "id": "admin",
            "display_name": "Admin User",
            "avatar": "https://server/avatar.png",
            "is_active": True,
        }
    }
    owner = ConferenceOwnerOutput.model_validate(raw_owner).model_dump(exclude_none=True)
    assert owner["user_id"] == "admin"
    assert owner["display_name"] == "Admin User"
    assert owner["avatar"] == "https://server/avatar.png"
    assert owner["id"] == "admin"

    raw_me = {
        "conference": {
            "owner": True,
            "moderator": True,
            "operator": False,
            "participant": True,
        }
    }
    me = ConferenceMeOutput.model_validate(raw_me).model_dump(exclude_none=True)
    assert me["is_owner"] is True
    assert me["is_moderator"] is True
    assert me["is_operator"] is False
    assert me["is_participant"] is True


def test_recording_output_and_list():
    raw = {
        "recording": {
            "id": 99,
            "conference_id": "conf-7",
            "topic": "Strategy Session",
            "name": "rec_099.mp4",
            "size": 1048576,
            "download_url": "https://server/rec/99/download",
        }
    }
    rec = RecordingOutput.model_validate(raw).model_dump(exclude_none=True)
    assert rec["recording_id"] == 99
    assert rec["conference_id"] == "conf-7"
    assert rec["conference_name"] == "Strategy Session"
    assert rec["file_name"] == "rec_099.mp4"
    assert rec["size_bytes"] == 1048576
    assert rec["id"] == 99
    assert rec["topic"] == "Strategy Session"

    raw_list = {"cnt": 1, "list": [raw["recording"]]}
    rec_list = RecordingListOutput.model_validate(raw_list).model_dump(exclude_none=True)
    assert rec_list["total"] == 1
    assert rec_list["recordings"][0]["recording_id"] == 99


def test_links_and_calendars():
    dl = DeeplinksOutput.model_validate(
        {"deeplinks": {"android": "tc://conf/android", "default": "tc://conf/default"}}
    ).model_dump(exclude_none=True)
    assert dl["android"] == "tc://conf/android"
    assert dl["default"] == "tc://conf/default"

    shared = SharedLinksOutput.model_validate(
        {
            "embedded": {"webrtc": "https://server/webrtc"},
            "rtsp_url": "rtsp://server/stream",
        }
    ).model_dump(exclude_none=True)
    assert shared["webrtc_url"] == "https://server/webrtc"
    assert shared["rtsp_url"] == "rtsp://server/stream"

    cal = CalendarsOutput.model_validate(
        {"calendars": {"google": "https://google.com/cal", "other": "https://other.com/cal"}}
    ).model_dump(exclude_none=True)
    assert cal["google_calendar_url"] == "https://google.com/cal"
    assert cal["other_calendar_url"] == "https://other.com/cal"


def test_action_success_and_helpers():
    act = ActionSuccessOutput(
        success=True,
        status="running",
        conference_id="conf-1",
        message="Started",
    ).model_dump(exclude_none=True)
    assert act["success"] is True
    assert act["status"] == "running"
    assert act["conference_id"] == "conf-1"

    reg = RegistrationOutput.model_validate(
        {
            "email_notification_created": True,
            "registration_token": "jwt-token-123",
        }
    ).model_dump(exclude_none=True)
    assert reg["email_notification_created"] is True
    assert reg["registration_token"] == "jwt-token-123"

    tr = TranslationsOutput.model_validate({"translations": ["ru", "en"]}).model_dump(exclude_none=True)
    assert tr["translations"] == ["ru", "en"]

    calc = CalculateConferencesOutput.model_validate(
        {
            "symmetric": {"max_podiums": 36},
        }
    ).model_dump(exclude_none=True)
    assert calc["symmetric"] == {"max_podiums": 36}


def test_address_book_output():
    raw = {
        "contacts": [
            {
                "id": "alice",
                "display_name": "Alice Cooper",
                "email": "alice@corp.com",
                "status": 1,
            }
        ],
        "next_page_id": 2,
    }
    ab = AddressBookOutput.model_validate(raw).model_dump(exclude_none=True)
    assert len(ab["contacts"]) == 1
    c = ab["contacts"][0]
    assert c["user_id"] == "alice"
    assert c["id"] == "alice"
    assert c["display_name"] == "Alice Cooper"
    assert c["email"] == "alice@corp.com"
    assert ab["next_page_id"] == 2


def test_ai_transcription_models():
    # Real GET /transcriptions and /transcriptions/{id} response item shape
    # (verified live on sai01t.trueconf.name, 2026-10-05); audio_url is
    # injected by the get_transcription tool, not returned by the API
    raw_item = {
        "id": 10,
        "conference_id": "conf-ai",
        "session_id": "sess-ai",
        "display_name": "AI Meeting",
        "duration": 120.5,
        "language": "ru",
        "transcription_status_id": 8,
        "recognition_progress": 100,
        "finished_at": "2026-10-05T22:09:55+03:00",
        "access_level": "admin",
        "tcs_id": 4,
        "status_note": None,
        "audio_url": "https://sai/audio/10",
        "transcription_url": "https://sai/t/10",
    }
    t = TranscriptionOutput.model_validate(raw_item).model_dump(exclude_none=True)
    assert t["transcription_id"] == 10
    assert t["id"] == 10
    assert t["conference_name"] == "AI Meeting"
    assert t["display_name"] == "AI Meeting"
    assert t["duration"] == 120.5
    assert t["language"] == "ru"
    assert t["transcription_status_id"] == 8
    assert t["recognition_progress"] == 100
    assert t["access_level"] == "admin"
    # raw id mapped to a human-readable label for the LLM
    assert t["status"] == "recognized"

    raw_list = {"transcriptions": [raw_item], "page": {"current": 1, "total": 1}}
    t_list = TranscriptionListOutput.model_validate(raw_list).model_dump(exclude_none=True)
    assert len(t_list["transcriptions"]) == 1
    assert t_list["transcriptions"][0]["transcription_id"] == 10

    # Real GET /transcriptions/{id}/lines response item shape (verified
    # against the AI Server UI bundle on 2026-10-05)
    raw_lines = {
        "lines": [
            {
                "call_id": "alice",
                "display_name": "Alice Cooper",
                "id": 10,
                "language": "ru",
                "line": "Hello world",
                "start_time": 0.0,
                "end_time": 5.2,
                "transcription_id": 3,
                "user_id": 42,
            }
        ]
    }
    lines = TranscriptionLinesOutput.model_validate(raw_lines).model_dump(exclude_none=True)
    assert len(lines["lines"]) == 1
    assert lines["lines"][0]["call_id"] == "alice"
    assert lines["lines"][0]["display_name"] == "Alice Cooper"
    assert lines["lines"][0]["line"] == "Hello world"
    assert lines["lines"][0]["language"] == "ru"

    raw_summary = {"summaries": [{"topic": "Key points", "text": "Discussed roadmap"}]}
    summary = TranscriptionSummaryOutput.model_validate(raw_summary).model_dump(exclude_none=True)
    assert len(summary["summaries"]) == 1
