from typing import Any

from fastmcp.utilities.types import File

from app.mcp import mcp, _request_file
from app.trueconf_api.models import ChatExportFilters


@mcp.tool(tags={"conference", "read"})
async def export_chat_messages(
    conference_id: str,
    date_from: int | None = None,
    date_to: int | None = None,
    from_call_id: str | None = None,
    to_call_id: str | None = None,
    message: str | None = None,
    session_id: str | None = None,
) -> File | dict[str, Any]:
    """Export conference chat messages as a CSV file.

    Returns the CSV file as an MCP File content block.

    Args:
        conference_id: Conference identifier
        date_from: Messages starting from this timestamp
        date_to: Messages up to this timestamp
        from_call_id: Filter by sender
        to_call_id: Filter by recipient
        message: Filter by message text
        session_id: Filter by session ID
    """
    filters = ChatExportFilters(
        date_from=date_from,
        date_to=date_to,
        from_call_id=from_call_id,
        to_call_id=to_call_id,
        message=message,
        session_id=session_id,
    )
    return await _request_file(
        "GET",
        f"conferences/{conference_id}/messages-export",
        format="csv",
        name=f"{conference_id}-chat.csv",
        params=filters.model_dump(exclude_none=True),
    )
