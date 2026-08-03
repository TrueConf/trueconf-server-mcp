from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import ConferenceNotifyRequest


@mcp.tool(tags={"conference", "write"})
async def notify_conference(
    conference_id: str,
    invitation_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Notify participants about a conference.

    Sends email/push notifications. If invitation_ids is empty, notifies all participants.

    Args:
        conference_id: Conference identifier
        invitation_ids: List of invitation IDs to notify. Empty list = notify all.
    """
    req = ConferenceNotifyRequest(invitations=invitation_ids)
    return await _request(
        "POST",
        f"conferences/{conference_id}/notify",
        json=req.model_dump(exclude_none=True) or None,
    )
