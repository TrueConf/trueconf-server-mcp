from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "read"})
async def get_conference_translations(conference_id: str) -> dict[str, Any]:
    """Get audio translation tracks (simultaneous interpretation) for a conference.

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/translations")
