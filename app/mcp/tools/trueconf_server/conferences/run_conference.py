from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "lifecycle"})
async def run_conference(conference_id: str) -> dict[str, Any]:
    """Start (launch) a conference.

    Args:
        conference_id: Conference identifier to start
    """
    raw = await _request("POST", f"conferences/{conference_id}/run")
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="running",
        conference_id=conference_id,
        message="Conference started successfully",
    ).model_dump(exclude_none=True)
