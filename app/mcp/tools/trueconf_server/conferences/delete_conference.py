from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "write", "dangerous"})
async def delete_conference(conference_id: str) -> dict[str, Any]:
    """Delete a conference by ID.

    Args:
        conference_id: Conference identifier to delete
    """
    raw = await _request("DELETE", f"conferences/{conference_id}")
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="deleted",
        conference_id=conference_id,
        message="Conference deleted successfully",
    ).model_dump(exclude_none=True)
