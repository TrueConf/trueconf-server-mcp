from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"conference", "read"})
async def get_conference_calendars(conference_id: str) -> dict[str, Any]:
    """Get calendar links for a conference (Google Calendar, Outlook, ICS URL).

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/calendars")
