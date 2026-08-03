from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"invitations", "read"})
async def list_invitations(conference_id: str) -> dict[str, Any]:
    """List all planned participants (invitations) for a conference.

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/invitations")
