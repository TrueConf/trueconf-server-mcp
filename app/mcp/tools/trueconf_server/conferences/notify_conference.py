from typing import Any

from app._client_api._trueconf_server.models import ActionSuccessOutput, ConferenceNotifyRequest
from app.mcp import _request, mcp


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
    raw = await _request(
        "POST",
        f"conferences/{conference_id}/notify",
        json=req.model_dump(exclude_none=True) or None,
    )
    if "error" in raw:
        return raw
    return ActionSuccessOutput(
        success=True,
        status="notified",
        conference_id=conference_id,
        message="Participants notification request accepted",
    ).model_dump(exclude_none=True)
