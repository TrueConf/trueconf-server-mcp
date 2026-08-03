from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import DeepLinksFilters


@mcp.tool(tags={"links", "read"})
async def get_deeplinks(
    conference_id: str,
    case: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    """Get deep links for a conference.

    Args:
        conference_id: Conference identifier
        case: Scenario for deeplink generation
        user: User authorization type
    """
    filters = DeepLinksFilters(case=case, user=user)
    return await _request(
        "GET", f"conferences/{conference_id}/deeplinks",
        params=filters.model_dump(exclude_none=True),
    )
