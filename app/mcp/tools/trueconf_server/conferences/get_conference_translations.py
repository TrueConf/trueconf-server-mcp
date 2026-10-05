from typing import Any

from app._client_api._trueconf_server.models import TranslationsOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"conference", "read"})
async def get_conference_translations(conference_id: str) -> dict[str, Any]:
    """Get audio translation tracks (simultaneous interpretation) for a conference.

    Args:
        conference_id: Conference identifier
    """
    raw = await _request("GET", f"conferences/{conference_id}/translations")
    if "error" in raw:
        return raw
    return TranslationsOutput.model_validate(raw).model_dump(exclude_none=True)
