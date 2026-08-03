from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"links", "read"})
async def get_shared_links(conference_id: str) -> dict[str, Any]:
    """Get shared/embedded links for a conference.

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/shared")
