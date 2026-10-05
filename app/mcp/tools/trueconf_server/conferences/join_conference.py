from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "write"})
async def join_conference(conference_id: str) -> dict[str, Any]:
    """Join an active conference session.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("POST", f"conferences/{conference_id}/join")
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="joined",
        conference_id=conference_id,
        message="Joined conference session successfully",
    ).model_dump(exclude_none=True)
