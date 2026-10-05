from typing import Any

from app._client_api._trueconf_server.models import SharedLinksOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"links", "read"})
async def get_shared_links(conference_id: str) -> dict[str, Any]:
    """Get shared/embedded links for a conference.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/shared")
    if "error" in raw:
        return raw
    return SharedLinksOutput.model_validate(raw).model_dump(exclude_none=True)
