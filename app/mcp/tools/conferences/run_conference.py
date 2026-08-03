from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "lifecycle"})
async def run_conference(conference_id: str) -> dict[str, Any]:
    """Start (launch) a conference.

    Args:
        conference_id: Conference identifier to start
    """
    return await _request("POST", f"conferences/{conference_id}/run")
