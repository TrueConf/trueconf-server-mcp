from typing import Any

from app._client_api._trueconf_server.models import ConferenceMeOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "read"})
async def get_conference_me(conference_id: str) -> dict[str, Any]:
    """Get the caller's roles in a conference.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/me")
    if "error" in raw:
        return raw
    return ConferenceMeOutput.model_validate(raw).model_dump(exclude_none=True)
