from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import ConferenceParticipantsFilters


@mcp.tool(tags={"conference", "read"})
async def get_conference_participants(
    conference_id: str,
    is_in_conf: bool | None = None,
    display_name: str | None = None,
    call_id: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Get participants of an active conference session.

    Args:
        conference_id: Conference identifier
        is_in_conf: Filter by whether participant is currently in conference
        display_name: Filter by display name
        call_id: Filter by participant call_id
        page: Page number
        page_size: Records per page
    """
    filters = ConferenceParticipantsFilters(
        is_in_conf=is_in_conf,
        display_name=display_name,
        call_id=call_id,
        page=page,
        page_size=page_size,
    )
    return await _request(
        "GET", f"conferences/{conference_id}/participants",
        params=filters.model_dump(exclude_none=True),
    )
