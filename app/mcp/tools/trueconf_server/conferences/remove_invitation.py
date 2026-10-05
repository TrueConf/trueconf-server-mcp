from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"invitations", "write"})
async def remove_invitation(conference_id: str, invitation_id: str) -> dict[str, Any]:
    """Remove a participant from a conference invitation list.

    Args:
        conference_id: Conference identifier
        invitation_id: Invitation identifier to remove
    """
    raw = await _request(
        "DELETE",
        f"conferences/{conference_id}/invitations/{invitation_id}",
    )
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="removed",
        conference_id=conference_id,
        message=f"Participant {invitation_id} removed from invitation list",
    ).model_dump(exclude_none=True)
