from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import CalculateConferencesFilters, ConferenceAccess


@mcp.tool(tags={"conference", "read"})
async def calculate_conferences(
    access: ConferenceAccess | None = None,
    multicast_enabled: bool | None = None,
) -> dict[str, Any]:
    """Calculate conference participant/podium scheme restrictions.

    Returns info about max podiums and participants for different conference types.

    Args:
        access: Conference access mode filter (private/public)
        multicast_enabled: Whether UDP Multicast mode is enabled
    """
    filters = CalculateConferencesFilters(
        access=access,
        multicast_enabled=multicast_enabled,
    )
    return await _request(
        "GET", "calculate/conferences",
        params=filters.model_dump(exclude_none=True),
    )
