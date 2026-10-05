from typing import Any

from app._client_api._trueconf_server.models import CalendarsOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "read"})
async def get_conference_calendars(conference_id: str) -> dict[str, Any]:
    """Get calendar links for a conference (Google Calendar, Outlook, ICS URL).

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/calendars")
    if "error" in raw:
        return raw
    return CalendarsOutput.model_validate(raw).model_dump(exclude_none=True)
