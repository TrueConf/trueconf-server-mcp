from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "read"})
async def get_conference_owner(conference_id: str) -> dict[str, Any]:
    """Get information about the conference owner.

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/owner")
