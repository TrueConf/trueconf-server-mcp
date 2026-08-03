from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"recordings", "read"})
async def get_recording(
    conference_id: str,
    recording_id: str,
) -> dict[str, Any]:
    """Get details of a specific conference recording.

    Args:
        conference_id: Conference identifier
        recording_id: Recording identifier
    """
    return await _request(
        "GET", f"conferences/{conference_id}/recordings/{recording_id}"
    )
