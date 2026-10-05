from typing import Any

from app._client_api._trueconf_server.models import InvitationListOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"invitations", "read"})
async def list_invitations(conference_id: str) -> dict[str, Any]:
    """List all planned participants (invitations) for a conference.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/invitations")
    if "error" in raw:
        return raw
    return InvitationListOutput.model_validate(raw).model_dump(exclude_none=True)
