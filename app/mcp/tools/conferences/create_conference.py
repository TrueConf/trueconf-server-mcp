import logging
from typing import Any

from fastmcp.server.dependencies import get_access_token

from app.mcp import mcp, _request, _auth_required_dict
from app.mcp.errors import make_error
from app.trueconf_api.mode_utils import _resolve_access, _resolve_mode
from app.trueconf_api.models import (
    ConferenceAccess,
    ConferenceCreate,
    ConferenceInvitationCreate,
    ConferenceSchedule,
    ScheduleType,
)
import pydantic

logger = logging.getLogger(__name__)


@mcp.tool(tags={"conference", "write"})
async def create_conference(
    topic: str,
    mode: str,
    owner: str | None = None,
    access: str = "private",
    conference_id: str | None = None,
    description: str | None = None,
    schedule_type: ScheduleType = "none",
    schedule_start_time: int | None = None,
    schedule_duration: int | None = None,
    invitations: list[dict[str, Any]] | None = None,
    allow_guests: bool = False,
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
        topic: Conference subject (1-240 chars)
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
        schedule_start_time: Scheduled start time (unix timestamp)
        schedule_duration: Scheduled duration in seconds
        invitations: List of invited participants, each with "id" (required)
                     and optional "display_name", "is_moderator".
                     The owner is always added automatically to invitations.
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
    if owner is None:
        token = get_access_token()
        if token is None:
            return _auth_required_dict()
        owner = token.client_id
        logger.info("Owner определён автоматически: %s", owner)
    schedule = ConferenceSchedule(
        type=schedule_type,
        start_time=schedule_start_time,
        duration=schedule_duration,
    )

    inv_list = [ConferenceInvitationCreate(id=owner)]
    if invitations:
        for inv in invitations:
            if inv.get("id") != owner:
                try:
                    inv_list.append(ConferenceInvitationCreate(**inv))
                except pydantic.ValidationError as e:
                    return make_error("invalid_invitation", detail=str(e.errors()))

    try:
        resolved_mode = _resolve_mode(mode)
    except ValueError as e:
        return make_error("invalid_mode", detail=str(e))
    resolved_access: ConferenceAccess = _resolve_access(access) or "private"

    conf = ConferenceCreate(
        topic=topic,
        owner=owner,
        mode=resolved_mode,
        access=resolved_access,
        id=conference_id,
        description=description,
        schedule=schedule,
        invitations=inv_list,
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
        "POST", "conferences", json=conf.model_dump(exclude_none=True)
    )
