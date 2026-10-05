from typing import Any

from app._client_api._trueconf_server.mode_utils import (
    _resolve_access,
    _resolve_mode,
    build_guest_rights,
)
from app._client_api._trueconf_server.models import ConferenceOutput, ConferenceUpdate, ScheduleType
from app.mcp import _request, mcp
from app.mcp.errors import make_error
from app.mcp.tools.trueconf_server.conferences.sai_utils import build_sai
from app.mcp.tools.trueconf_server.conferences.schedule_utils import (
    build_schedule,
    resolve_partial_schedule,
    schedule_update_is_partial,
)


# C901 suppressed deliberately: tool entry point; the complexity is a linear chain
# of guard clauses (guest_rights validation, partial-schedule inheritance)
# whose merge semantics are documented as fragile — see AGENTS.md. Refactoring
# here risks breaking the documented invariants.
@mcp.tool(tags={"conference", "write"})
async def update_conference(  # noqa: C901
    conference_id: str,
    conference_name: str | None = None,
    owner: str | None = None,
    mode: str | None = None,
    access: str | None = None,
    description: str | None = None,
    schedule_type: ScheduleType | None = None,
    schedule_date: str | None = None,
    schedule_duration: int | None = None,
    schedule_days: list[str] | None = None,
    schedule_time: str | None = None,
    timezone: str | None = None,
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
    transcription_enabled: bool | None = None,
    transcription_language: str | None = None,
    transcription_auto_detect_language: bool | None = None,
) -> dict[str, Any]:
    """Update an existing conference. Only provided fields will be updated.

    Inheritance: when guest_rights is passed without access, or the schedule
    change is partial, the missing pieces are inherited from the
    conference's CURRENT state (one GET). Explicitly provided values ALWAYS
    override inherited ones — inheritance only fills gaps, it never
    replaces your input (an explicit timezone wins over the inherited
    offset, an explicit access wins over the current state, etc.).

    Args:
        conference_id: Conference identifier to update
        conference_name: Conference name / subject
        owner: User identifier of the conference owner
        mode: Conference mode. Accepts exact values or descriptions:
              PxP / 'all on screen' / 'все на экране' — gallery view
              OxP / 'lecture' / 'лекция' — video lecture
              S|L / 'role-based' / 'по ролям' — speaker and listeners
              S|L Auto / 'auto' / 'авто' — auto role selector
        access: Access type: private / public / 'закрытая' / 'открытая'
        description: Conference description
        schedule_type: Schedule type. 'once' or 'week' to (re)schedule
            (with the fields below), 'none' to CLEAR the existing schedule.
            Omit (default) to leave the schedule untouched. When only some
            fields are provided, the missing ones (schedule_duration,
            schedule_time, schedule_days, timezone, the date) are inherited
            from the conference's CURRENT schedule — e.g. to move the start
            time, pass only schedule_time. Requires the conference to
            already have a schedule; otherwise the usual required-field
            error applies. Explicitly provided values always override the
            inherited ones.
        schedule_date: Date for schedule_type='once' or 'week'. A 'YYYY-MM-DD'
            date or an English phrase resolved against today on the server:
            'next Monday', 'this Wednesday', 'Friday', 'tomorrow',
            'in 3 days', 'next week'. Optionally include the local time:
            'next Monday at 13:00'.
        schedule_duration: Scheduled duration in seconds
        schedule_days: Weekdays for schedule_type='week', e.g.
            ['monday', 'wednesday']. One of: monday, tuesday, wednesday,
            thursday, friday, saturday, sunday. If omitted, the weekday of
            schedule_date is used.
        schedule_time: Start time of day as local "HH:MM", e.g. "13:00".
            Required unless embedded in schedule_date or inherited from the
            current schedule on a partial update. Converted internally to
            UTC.
        timezone: IANA timezone name (e.g. "Europe/Moscow") or a fixed UTC
            offset (e.g. "+3", "-5", "UTC+3"). Needed to convert the local
            schedule_time to UTC; on a partial update the current
            conference's offset is inherited when omitted.
        guest_rights: With access='public' guests are enabled and granted all
            capabilities by default. Pass a list of capability keys to DISABLE
            for guests. Only takes effect with access='public'; if access is
            omitted, the conference's current access is checked, so rights
            can be changed on an already-public conference without re-sending
            access. An explicitly provided access always takes precedence
            over the current state. NOTE: this is a DENY list — the listed capabilities are
            revoked, everything else stays enabled. To allow guests ONLY certain capabilities, list every
            OTHER key here. Available keys:
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
        transcription_enabled: Enable conference transcription (the AI Server
            records and transcribes the conference). Maps to the API's
            sai.recording_enabled.
        transcription_language: Recognition language for transcription, e.g.
            'ru', 'en'. Only meaningful when transcription_enabled=True.
            Maps to the API's sai.recognition_language.
        transcription_auto_detect_language: Auto-detect the recognition
            language instead of using transcription_language. Maps to the
            API's sai.auto_recognition_enabled.
    """
    try:
        resolved_mode = _resolve_mode(mode) if mode is not None else None
    except ValueError as e:
        return make_error("invalid_mode", detail=str(e))
    resolved_access = _resolve_access(access)

    if guest_rights and resolved_access is not None and resolved_access != "public":
        return make_error(
            "guest_rights_requires_public_access",
            message=(
                "guest_rights only takes effect with access='public' "
                "(guests are enabled by access=public). "
                "Set access='public' or drop guest_rights."
            ),
        )

    schedule_is_partial = False
    if schedule_type in ("once", "week"):
        schedule_is_partial = schedule_update_is_partial(
            schedule_type=schedule_type,
            schedule_date=schedule_date,
            duration=schedule_duration,
            days=schedule_days,
            time=schedule_time,
            timezone=timezone,
        )

    # Partial updates (guest_rights without access, partial schedule) need
    # the conference's current state — fetch it once, reuse for both.
    current: dict[str, Any] | None = None
    if (guest_rights and resolved_access is None) or schedule_is_partial:
        current = await _request("GET", f"conferences/{conference_id}")
        if isinstance(current, dict) and "error" in current:
            return current
        # The API wraps the conference in an envelope: {"conference": {...}}.
        if isinstance(current, dict) and isinstance(current.get("conference"), dict):
            current = current["conference"]

    if guest_rights and resolved_access is None:
        current_access = current.get("access") if isinstance(current, dict) else None
        if current_access != "public":
            return make_error(
                "guest_rights_requires_public_access",
                message=(
                    "guest_rights only takes effect with access='public' "
                    "(guests are enabled by access=public). This conference "
                    f"is '{current_access or 'unknown'}' — set access='public' "
                    "or drop guest_rights."
                ),
            )

    # Omitting schedule_type (default None) leaves the existing schedule
    # untouched — exclude_none keeps it out of the PATCH. An explicit
    # 'none' clears it (schedule {"type": "none"} is the documented PATCH
    # way to unschedule); 'once'/'week' build a new one from local values,
    # inheriting any missing required fields from the current schedule.
    schedule = None
    if schedule_type is not None:
        if schedule_is_partial:
            current_schedule = current.get("schedule") if isinstance(current, dict) else None
            schedule, schedule_error = resolve_partial_schedule(
                schedule_type=schedule_type,
                schedule_date=schedule_date,
                duration=schedule_duration,
                days=schedule_days,
                time=schedule_time,
                timezone=timezone,
                current=current_schedule,
            )
        else:
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
    elif any(
        v is not None
        for v in (
            schedule_date,
            schedule_duration,
            schedule_days,
            schedule_time,
        )
    ):
        return make_error(
            "invalid_schedule",
            message=(
                "schedule_type is required when schedule fields are provided "
                "('once' or 'week' to (re)schedule, 'none' to clear)."
            ),
        )

    try:
        rights = build_guest_rights(guest_rights)
    except ValueError as e:
        return make_error("invalid_guest_rights", detail=str(e))

    update = ConferenceUpdate(
        topic=conference_name,
        owner=owner,
        mode=resolved_mode,
        access=resolved_access,
        description=description,
        schedule=schedule,
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
        sai=build_sai(
            transcription_enabled,
            transcription_language,
            transcription_auto_detect_language,
        ),
    )
    raw = await _request(
        "PATCH",
        f"conferences/{conference_id}",
        json=update.model_dump(exclude_none=True),
    )
    if "error" in raw:
        return raw
    return ConferenceOutput.model_validate(raw).model_dump(exclude_none=True)
