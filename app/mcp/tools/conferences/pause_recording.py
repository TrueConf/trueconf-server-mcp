from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"recordings", "write"})
async def pause_recording(conference_id: str) -> dict[str, Any]:
    """Pause recording a conference.

    Args:
        conference_id: Conference identifier
    """
    return await _request("POST", f"conferences/{conference_id}/recordings/pause")
