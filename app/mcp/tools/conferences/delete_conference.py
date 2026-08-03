from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "write", "dangerous"})
async def delete_conference(conference_id: str) -> dict[str, Any]:
    """Delete a conference by ID.

    Args:
        conference_id: Conference identifier to delete
    """
    return await _request("DELETE", f"conferences/{conference_id}")
