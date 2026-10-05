from typing import Any

from app._client_api._trueconf_server.models import ConferenceOwnerOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "read"})
async def get_conference_owner(conference_id: str) -> dict[str, Any]:
    """Get information about the conference owner.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/owner")
    if "error" in raw:
        return raw
    return ConferenceOwnerOutput.model_validate(raw).model_dump(exclude_none=True)
