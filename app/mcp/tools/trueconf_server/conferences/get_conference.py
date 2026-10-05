from typing import Any

from app._client_api._trueconf_server.models import ConferenceOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "read"})
async def get_conference(conference_id: str) -> dict[str, Any]:
    """Get a conference by ID.

    Args:
        conference_id: Unique conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}")
    if "error" in raw:
        return raw
    return ConferenceOutput.model_validate(raw).model_dump(exclude_none=True)
