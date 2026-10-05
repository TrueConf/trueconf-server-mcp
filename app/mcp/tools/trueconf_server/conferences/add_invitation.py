from typing import Any

from app._client_api._trueconf_server.models import ConferenceInvitationAdd, InvitationOutput
from app.mcp import _request, mcp


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
    raw = await _request(
        "POST",
        f"conferences/{conference_id}/invitations",
        json={"invitation": invitation.model_dump(exclude_none=True)},
    )
    if "error" in raw:
        return raw
    return InvitationOutput.model_validate(raw).model_dump(exclude_none=True)
