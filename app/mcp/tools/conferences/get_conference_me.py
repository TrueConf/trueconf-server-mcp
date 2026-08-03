from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "read"})
async def get_conference_me(conference_id: str) -> dict[str, Any]:
    """Get the caller's roles in a conference.

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/me")
