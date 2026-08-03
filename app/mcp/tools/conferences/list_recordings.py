from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import RecordingSearchFilters


@mcp.tool(tags={"recordings", "read"})
async def list_recordings(
    conference_id: str,
    page: int | None = None,
    page_size: int | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    name: str | None = None,
    owner: str | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    """List recordings for a conference.

    Args:
        conference_id: Conference identifier
        page: Page number
        page_size: Records per page
        date_from: Filter recordings from this timestamp
        date_to: Filter recordings until this timestamp
        name: Filter by recording filename
        owner: Filter by owner user_id
        topic: Filter by conference topic
    """
    filters = RecordingSearchFilters(
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        name=name,
        owner=owner,
        topic=topic,
    )
    return await _request(
        "GET", f"conferences/{conference_id}/recordings",
        params=filters.model_dump(exclude_none=True),
    )
