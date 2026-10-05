from typing import Any

from app._client_api._trueconf_server.models import InvitationOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"invitations", "read"})
async def get_invitation(
    conference_id: str,
    invitation_id: str,
) -> dict[str, Any]:
    """Get details of a specific conference invitation.

    Args:
        conference_id: Conference identifier
        invitation_id: Invitation identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/invitations/{invitation_id}")
    if "error" in raw:
        return raw
    return InvitationOutput.model_validate(raw).model_dump(exclude_none=True)
