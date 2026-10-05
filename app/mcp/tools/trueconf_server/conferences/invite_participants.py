from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput
from app.mcp import _request, mcp


@mcp.tool(tags={"invitations", "write"})
async def invite_participants(
    conference_id: str,
    participant_ids: list[str],
) -> dict[str, Any]:
    """Invite participants to an active conference session.

    Args:
        conference_id: Conference identifier
        participant_ids: List of user identifiers to invite
    """
    raw = await _request(
        "POST",
        f"conferences/{conference_id}/invite",
        json={"participants": participant_ids},
    )
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="invited",
        conference_id=conference_id,
        message=f"Invited {len(participant_ids)} participant(s) to conference",
    ).model_dump(exclude_none=True)
