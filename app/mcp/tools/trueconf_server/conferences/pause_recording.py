from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"recordings", "write"})
async def pause_recording(conference_id: str) -> dict[str, Any]:
    """Pause recording a conference.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("POST", f"conferences/{conference_id}/recordings/pause")
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="recording_paused",
        conference_id=conference_id,
        message="Conference recording paused successfully",
    ).model_dump(exclude_none=True)
