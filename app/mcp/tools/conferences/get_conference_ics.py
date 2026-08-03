from typing import Any

from fastmcp.utilities.types import File

from app.mcp import mcp, _request_file


@mcp.tool(tags={"conference", "read"})
async def get_conference_ics(
    conference_id: str,
) -> File | dict[str, Any]:
    """Get ICS calendar file for a conference.

    Returns the ICS file as an MCP File content block.

    Args:
        conference_id: Conference identifier
    """
    return await _request_file(
        "GET",
        f"conferences/{conference_id}/ics",
        format="ics",
        name=f"{conference_id}.ics",
    )
