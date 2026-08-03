from typing import Any

from app.mcp import mcp, _request


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
    return await _request(
        "GET", f"conferences/{conference_id}/invitations/{invitation_id}"
    )
