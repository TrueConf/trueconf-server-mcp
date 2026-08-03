from typing import Any

from app.mcp import mcp, _request


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
    return await _request(
        "POST",
        f"conferences/{conference_id}/invite",
        json={"participants": participant_ids},
    )
