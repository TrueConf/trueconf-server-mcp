from typing import Any

from app._client_api._trueconf_server.models import (
    CalculateConferencesFilters,
    CalculateConferencesOutput,
    ConferenceAccess,
)
from app.mcp import _request, mcp


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
    raw = await _request(
        "GET",
        "calculate/conferences",
        params=filters.model_dump(exclude_none=True),
    )
    if "error" in raw:
        return raw
    return CalculateConferencesOutput.model_validate(raw).model_dump(exclude_none=True)
