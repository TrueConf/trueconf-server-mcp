from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "read"})
async def get_conference(conference_id: str) -> dict[str, Any]:
    """Get a conference by ID.

    Args:
        conference_id: Unique conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}")
