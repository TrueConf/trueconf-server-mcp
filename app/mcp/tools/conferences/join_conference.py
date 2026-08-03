from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "write"})
async def join_conference(conference_id: str) -> dict[str, Any]:
    """Join an active conference session.

    Args:
        conference_id: Conference identifier
    """
    return await _request("POST", f"conferences/{conference_id}/join")
