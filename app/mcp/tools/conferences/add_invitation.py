from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import ConferenceInvitationAdd


@mcp.tool(tags={"invitations", "write"})
async def add_invitation(
    conference_id: str,
    participant_id: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Add a participant to a conference invitation list.

    Args:
        conference_id: Conference identifier
        participant_id: User identifier to invite
        display_name: Display name for the participant
    """
    invitation = ConferenceInvitationAdd(
        id=participant_id,
        display_name=display_name,
    )
    return await _request(
        "POST",
        f"conferences/{conference_id}/invitations",
        json={"invitation": invitation.model_dump(exclude_none=True)},
    )
