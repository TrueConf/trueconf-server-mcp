from typing import Any

from app._client_api._trueconf_server.models import RecordingOutput
from app.mcp import _request, mcp


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
    raw = await _request("GET", f"conferences/{conference_id}/recordings/{recording_id}")
    if "error" in raw:
        return raw
    return RecordingOutput.model_validate(raw).model_dump(exclude_none=True)
