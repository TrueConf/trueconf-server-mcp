from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"invitations", "write"})
async def remove_invitation(
    conference_id: str, invitation_id: str
) -> dict[str, Any]:
    """Remove a participant from a conference invitation list.

    Args:
        conference_id: Conference identifier
        invitation_id: Invitation identifier to remove
    """
    return await _request(
        "DELETE",
        f"conferences/{conference_id}/invitations/{invitation_id}",
    )
