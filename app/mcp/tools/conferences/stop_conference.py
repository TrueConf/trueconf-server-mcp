from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "lifecycle"})
async def stop_conference(conference_id: str) -> dict[str, Any]:
    """Stop a running conference.

    Args:
        conference_id: Conference identifier to stop
    """
    return await _request("POST", f"conferences/{conference_id}/stop")
