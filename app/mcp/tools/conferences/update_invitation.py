from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import ConferenceInvitationUpdate


@mcp.tool(tags={"invitations", "write"})
async def update_invitation(
    conference_id: str,
    invitation_id: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Update a conference invitation (e.g. change display name).

    Args:
        conference_id: Conference identifier
        invitation_id: Invitation identifier
        display_name: New display name for the participant
    """
    invitation = ConferenceInvitationUpdate(display_name=display_name)
    return await _request(
        "PATCH",
        f"conferences/{conference_id}/invitations/{invitation_id}",
        json={"invitation": invitation.model_dump(exclude_none=True)},
    )
