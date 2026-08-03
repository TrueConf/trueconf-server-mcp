from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.mode_utils import _resolve_mode
from app.trueconf_api.models import ConferenceSearchFilters


@mcp.tool(tags={"conference", "read"})
async def list_conferences(
    topic: str | None = None,
    owner: str | None = None,
    state: str | None = None,
    access: str | None = None,
    mode: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
    sort_field: str | None = None,
    sort_order: int | None = None,
    timezone: str | None = None,
    after: int | None = None,
    before: int | None = None,
    topic_cid_contains: str | None = None,
) -> dict[str, Any]:
    """Search and list conferences with optional filters.

    Args:
        topic: Filter by conference name
        owner: Filter by owner user_id
        state: Filter by conference state
        access: Filter by access type (private/public)
        mode: Filter by conference mode (PxP/OxP/S|L/S|L Auto or descriptions
              like 'lecture'/'лекция')
        page: Page number
        page_size: Number of records per page
        sort_field: Field to sort by
        sort_order: Sort order (0=asc, 1=desc)
        timezone: Timezone for the request
        after: Schedule timestamp after
        before: Schedule timestamp before
        topic_cid_contains: Search by name or conference ID
    """
    resolved_mode = _resolve_mode(mode) if mode is not None else None
    params: dict[str, Any] = ConferenceSearchFilters(
        topic=topic,
        owner=owner,
        state=state,
        access=access,
        mode=resolved_mode,
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_order=sort_order,
        timezone=timezone,
        after=after,
        before=before,
        topic_cid_contains=topic_cid_contains,
    ).model_dump(exclude_none=True)
    return await _request("GET", "conferences", params=params)
