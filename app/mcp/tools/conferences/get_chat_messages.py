from typing import Any

from app.mcp import mcp, _request


@mcp.tool(tags={"chat", "read"})
async def get_chat_messages(conference_id: str) -> dict[str, Any]:
    """Get chat messages from a conference.

    Args:
        conference_id: Conference identifier
    """
    return await _request("GET", f"conferences/{conference_id}/messages")
