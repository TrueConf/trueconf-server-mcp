from typing import Any

from app._client_api._trueconf_server.models import DeepLinksFilters, DeeplinksOutput
from app.mcp import _request, mcp


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
    raw = await _request(
        "GET",
        f"conferences/{conference_id}/deeplinks",
        params=filters.model_dump(exclude_none=True),
    )
    if "error" in raw:
        return raw
    return DeeplinksOutput.model_validate(raw).model_dump(exclude_none=True)
