from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "lifecycle"})
async def stop_conference(conference_id: str) -> dict[str, Any]:
    """Stop a running conference.

    Args:
        conference_id: Conference identifier to stop
    """
    raw = await _request("POST", f"conferences/{conference_id}/stop")
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="stopped",
        conference_id=conference_id,
        message="Conference stopped successfully",
    ).model_dump(exclude_none=True)
