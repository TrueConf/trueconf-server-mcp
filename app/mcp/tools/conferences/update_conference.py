from typing import Any

from app.mcp import mcp, _request
from app.mcp.errors import make_error
from app.trueconf_api.mode_utils import _resolve_access, _resolve_mode
from app.trueconf_api.models import (
    ConferenceSchedule,
    ConferenceUpdate,
    ScheduleType,
)


@mcp.tool(tags={"conference", "write"})
async def update_conference(
    conference_id: str,
    topic: str | None = None,
    owner: str | None = None,
    mode: str | None = None,
    access: str | None = None,
    description: str | None = None,
    schedule_type: ScheduleType = "none",
    schedule_start_time: int | None = None,
    schedule_duration: int | None = None,
    allow_guests: bool | None = None,
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
    """Update an existing conference. Only provided fields will be updated.

    Args:
        conference_id: Conference identifier to update
        topic: Conference subject
        owner: User identifier of the conference owner
        mode: Conference mode. Accepts exact values or descriptions:
              PxP / 'all on screen' / 'все на экране' — gallery view
              OxP / 'lecture' / 'лекция' — video lecture
              S|L / 'role-based' / 'по ролям' — speaker and listeners
              S|L Auto / 'auto' / 'авто' — auto role selector
        access: Access type: private / public / 'закрытая' / 'открытая'
        description: Conference description
        schedule_type: Schedule type: none, once, week
        schedule_start_time: Scheduled start time (unix timestamp)
        schedule_duration: Scheduled duration in seconds
        allow_guests: Allow guest access
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
    """
    try:
        resolved_mode = _resolve_mode(mode) if mode is not None else None
    except ValueError as e:
        return make_error("invalid_mode", detail=str(e))
    resolved_access = _resolve_access(access)

    # Build schedule only when schedule params are explicitly provided —
    # otherwise None so exclude_none keeps the existing schedule untouched.
    has_schedule = (
        any(v is not None for v in (schedule_start_time, schedule_duration))
        or schedule_type != "none"
    )
    schedule = (
        ConferenceSchedule(
            type=schedule_type,
            start_time=schedule_start_time,
            duration=schedule_duration,
        )
        if has_schedule
        else None
    )

    update = ConferenceUpdate(
        topic=topic,
        owner=owner,
        mode=resolved_mode,
        access=resolved_access,
        description=description,
        schedule=schedule,
        allow_guests=allow_guests,
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
        "PATCH",
        f"conferences/{conference_id}",
        json=update.model_dump(exclude_none=True),
    )
