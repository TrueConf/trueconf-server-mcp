"""MCP prompts registered on the FastMCP server instance.

Importing this module is a side-effect registration: `conference_help`
becomes discoverable by MCP clients (e.g. via `mcp prompts list`).
"""

from app.mcp import mcp


@mcp.prompt()
async def conference_help() -> str:
    """Describe available conference management capabilities."""
    return (
        "You can manage TrueConf Server conferences with the following tools:\n"
        "- list_conferences: Search and list conferences\n"
        "- get_conference: Get conference details by ID\n"
        "- create_conference: Create a new conference\n"
        "- update_conference: Update conference settings\n"
        "- delete_conference: Delete a conference\n"
        "- run_conference: Start a conference\n"
        "- stop_conference: Stop a running conference\n"
        "- list_invitations / add_invitation / remove_invitation: Manage participants\n"
        "- invite_participants: Invite participants to active session\n"
        "- list_recordings / start_recording / stop_recording / pause_recording: Manage recordings\n"
        "- get_deeplinks / get_shared_links: Get conference links\n"
        "- get_chat_messages: Read conference chat\n"
    )
