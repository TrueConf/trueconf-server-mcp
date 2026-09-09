import logging
from typing import Any

from fastmcp.server.dependencies import get_access_token

from app.mcp import mcp, _request, _auth_required_dict
from app.mcp.errors import make_error
from app.trueconf_api.mode_utils import (
    _resolve_access,
    _resolve_mode,
    build_guest_rights,
)
from app.trueconf_api.models import (
    ConferenceAccess,
    ConferenceCreate,
    ConferenceInvitationCreate,
    ConferenceRegistrationCreate,
    ScheduleType,
)
from app.mcp.tools.conferences.schedule_utils import build_schedule
import pydantic

logger = logging.getLogger(__name__)


@mcp.tool(tags={"conference", "write"})
async def create_conference(
    conference_name: str,
    mode: str,
    owner: str | None = None,
    access: str = "private",
    conference_id: str | None = None,
    description: str | None = None,
    schedule_type: ScheduleType = "none",
    schedule_date: str | None = None,
    schedule_duration: int | None = None,
    schedule_days: list[str] | None = None,
    schedule_time: str | None = None,
    timezone: str | None = None,
    invitations: list[dict[str, Any]] | None = None,
    registration_enabled: bool | None = None,
    registration_start_at: int | None = None,
    registration_end_at: int | None = None,
    registration_participants_limit: int | None = None,
    guest_rights: list[str] | None = None,
    auto_invite: int | None = None,
    auto_termination_enabled: bool | None = None,
    broadcast_enabled: bool | None = None,
    max_participants: int | None = None,
    max_podiums: int | None = None,
    on_join_mute_camera: bool | None = None,
    on_join_mute_mic: bool | None = None,
    pin: str | None = None,
    recording_enabled: bool | None = None,
    tags: list[str] | None = None,
    waiting_room_enabled: bool | None = None,
) -> dict[str, Any]:
    """Create a new conference.

    Args:
        conference_name: Conference name / subject (1-240 chars).
        mode: Conference mode. Accepts exact values or descriptions:
              PxP / 'all on screen' / 'все на экране' — gallery view
              OxP / 'lecture' / 'лекция' — video lecture
              S|L / 'role-based' / 'по ролям' — speaker and listeners
              S|L Auto / 'auto' / 'авто' — auto role selector
        owner: User identifier of the conference owner. If not specified,
               the authenticated user is used automatically.
        access: Access type: private or public
        conference_id: Custom conference ID (auto-generated if not specified)
        description: Conference description
        schedule_type: Schedule type: none, once, week
        schedule_date: Date for schedule_type='once' or 'week'. A 'YYYY-MM-DD'
            date or an English phrase resolved against today on the server:
            'next Monday', 'this Wednesday', 'Friday', 'tomorrow',
            'the day after tomorrow', 'in 3 days', 'in 2 weeks',
            'two weeks from now', 'next week', 'the week after next'.
            Optionally include the local time: 'next Monday at 13:00'.
        schedule_duration: Scheduled duration in seconds. Required for
            schedule_type='once'/'week' (the server rejects scheduled
            conferences without it).
        schedule_days: Weekdays for schedule_type='week', e.g.
            ['monday', 'wednesday']. One of: monday, tuesday, wednesday,
            thursday, friday, saturday, sunday. If omitted, the weekday of
            schedule_date is used.
        schedule_time: Start time of day as local "HH:MM", e.g. "13:00".
            Required for scheduled conferences unless it is embedded in
            schedule_date (e.g. 'next Monday at 13:00'). Converted internally
            to UTC.
        timezone: IANA timezone name (e.g. "Europe/Moscow") or a fixed UTC
            offset (e.g. "+3", "-5", "UTC+3"). Required for scheduled
            conferences so the local schedule_time can be converted to UTC.
        invitations: List of invited participants, each with "id" (required)
                      and optional "display_name", "is_moderator".
                      The owner is always added automatically to invitations.
        registration_enabled: Enable participant registration (webinar mode).
                      Default registration fields (display_name, email) are
                      provided by the server.
        registration_start_at: Registration window start, unix timestamp (seconds).
                      Requires registration_enabled=True.
        registration_end_at: Registration window end, unix timestamp (seconds).
                      Requires registration_enabled=True.
        registration_participants_limit: Max number of registered participants.
                      Requires registration_enabled=True.
        guest_rights: With access='public' guests are enabled and granted all
                     capabilities by default. Pass a list of capability keys
                     to DISABLE for guests (e.g. ['file_transfer_send',
                     'white_board_send']). Ignored unless access='public'.
                     NOTE: this is a DENY list — the listed capabilities are
                     revoked, everything else stays enabled. To allow guests
                     ONLY certain capabilities, list every OTHER key here.
                     Example: allow guests only video+audio+chat →
                     guest_rights=['desktop_sharing','file_transfer_send',
                     'file_transfer_rcv','recording','remote_desktop_control',
                     'slide_show_rcv','slide_show_send','white_board_rcv',
                     'white_board_send'].
                     Available keys:
                     - audio_rcv: hear other participants
                     - audio_send: speak / transmit audio
                     - chat_rcv: receive chat messages
                     - chat_send: send chat messages
                     - desktop_sharing: share screen
                     - file_transfer_rcv: receive files
                     - file_transfer_send: send files
                     - recording: record the conference
                     - remote_desktop_control: control a shared remote desktop
                     - slide_show_rcv: view slides (presentations/meeting rooms)
                     - slide_show_send: present slides
                     - video_rcv: see other participants' video
                     - video_send: transmit video (camera)
                     - white_board_rcv: view the whiteboard
                     - white_board_send: edit the whiteboard
        auto_invite: Auto-invite setting
        auto_termination_enabled: Auto-end conference when duration expires
        broadcast_enabled: Enable broadcast
        max_participants: Max participants limit
        max_podiums: Max podium participants
        on_join_mute_camera: Mute camera on join
        on_join_mute_mic: Mute microphone on join
        pin: PIN code for conference
        recording_enabled: Enable recording
        tags: Conference tags
        waiting_room_enabled: Enable waiting room

    Examples:
        - create_conference(conference_name='Встреча', mode='PxP')
        - create_conference(conference_name='Синк', mode='S|L',
          schedule_type='once', schedule_date='next Monday at 13:00',
          schedule_duration=3600, timezone='Europe/Moscow')
        - create_conference(conference_name='Еженедельный стендап',
          mode='PxP', schedule_type='week', schedule_days=['monday'],
          schedule_time='09:00', timezone='Europe/Moscow')
    """
    if owner is None:
        token = get_access_token()
        if token is None:
            return _auth_required_dict()
        owner = token.client_id
        logger.info("Owner определён автоматически: %s", owner)
    schedule, schedule_error = build_schedule(
        schedule_type=schedule_type,
        schedule_date=schedule_date,
        duration=schedule_duration,
        days=schedule_days,
        time=schedule_time,
        timezone=timezone,
    )
    if schedule_error is not None:
        return schedule_error

    inv_list = [ConferenceInvitationCreate(id=owner)]
    if invitations:
        for inv in invitations:
            if inv.get("id") != owner:
                try:
                    inv_list.append(ConferenceInvitationCreate(**inv))
                except pydantic.ValidationError as e:
                    errors = e.errors()
                    # Detect the common "missing id" failure (e.g. a weak LLM
                    # wraps keys in extra quotes: {"\"id\"": ...}). Give a
                    # human-readable instruction instead of raw pydantic.
                    missing_id = [
                        err
                        for err in errors
                        if err.get("type") == "missing" and err.get("loc") == ("id",)
                    ]
                    if missing_id and len(missing_id) == len(errors):
                        return make_error(
                            "invalid_invitation",
                            message=(
                                "Каждый участник требует ключ 'id' (без кавычек), "
                                "например [{'id': 'alice'}]. "
                                f"Получено: {inv!r}"
                            ),
                        )
                    return make_error("invalid_invitation", detail=str(errors))

    try:
        resolved_mode = _resolve_mode(mode)
    except ValueError as e:
        return make_error("invalid_mode", detail=str(e))
    resolved_access: ConferenceAccess = _resolve_access(access) or "private"

    registration = None
    if any(
        v is not None
        for v in (
            registration_enabled,
            registration_start_at,
            registration_end_at,
            registration_participants_limit,
        )
    ):
        if registration_enabled is not True:
            return make_error(
                "invalid_registration",
                message=(
                    "registration_start_at / registration_end_at / "
                    "registration_participants_limit require "
                    "registration_enabled=True."
                ),
            )
        registration = ConferenceRegistrationCreate(
            enabled=True,
            start_at=registration_start_at,
            end_at=registration_end_at,
            participants_limit=registration_participants_limit,
            participants_limit_enabled=(
                True if registration_participants_limit is not None else None
            ),
        )

    if guest_rights and resolved_access != "public":
        return make_error(
            "guest_rights_requires_public_access",
            message=(
                "guest_rights only takes effect with access='public' "
                "(guests are enabled by access=public). "
                "Set access='public' or drop guest_rights."
            ),
        )

    try:
        rights = build_guest_rights(guest_rights)
    except ValueError as e:
        return make_error("invalid_guest_rights", detail=str(e))

    conf = ConferenceCreate(
        topic=conference_name,
        owner=owner,
        mode=resolved_mode,
        access=resolved_access,
        id=conference_id,
        description=description,
        schedule=schedule,
        invitations=inv_list,
        registration=registration,
        rights=rights,
        auto_invite=auto_invite,
        auto_termination_enabled=auto_termination_enabled,
        broadcast_enabled=broadcast_enabled,
        max_participants=max_participants,
        max_podiums=max_podiums,
        on_join_mute_camera=on_join_mute_camera,
        on_join_mute_mic=on_join_mute_mic,
        pin=pin,
        recording_enabled=recording_enabled,
        tags=tags,
        waiting_room_enabled=waiting_room_enabled,
    )
    return await _request(
        "POST", "conferences", json=conf.model_dump(exclude_none=True)
    )
