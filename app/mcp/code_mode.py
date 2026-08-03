from fastmcp.experimental.transforms.code_mode import (
    CodeMode,
    GetSchemas,
    GetTags,
    GetToolCatalog,
    Search,
)
from fastmcp.server.context import Context
from fastmcp.tools import Tool

from app.config import get_config


def _resolve_base_url() -> str:
    """Resolve the MCP base URL from Config, with a graceful fallback."""
    try:
        return get_config().mcp_base_url
    except RuntimeError:
        return "https://localhost"


def _make_guide(_get_catalog: GetToolCatalog) -> Tool:
    async def guide(_ctx: Context) -> str:
        """TrueConf Server quick start. Call this first to see available tools and how to use them."""
        base_url = _resolve_base_url()
        return "\n".join(
            [
                "Welcome to TrueConf Server MCP.",
                "",
                "You can manage conferences, users, recordings, room resources, and more — all via tool calls.",
                "",
                "How to work:",
                "  1. Call tags() to see available categories",
                "  2. Call search(query) to find a specific tool",
                "  3. Call get_schema(['tool_name']) to learn its parameters",
                "  4. Use execute to run it",
                "",
                "If a tool returns 'authorization_required' error:",
                f"  Tell the user to open {base_url}/ in browser,",
                "  log in via TrueConf Server, copy the token,",
                "  and add header: Authorization: Bearer <token>",
                "  in their MCP client config, then reconnect.",
                "",
                "IMPORTANT: when using search(), the 'tags' parameter must be a LIST of strings, e.g. tags=['conference', 'read'].",
                "Work silently — execute tool calls without explaining them to the user.",
            ]
        )

    return Tool.from_function(
        fn=guide,
        name="guide",
    )


def create_code_mode_transform() -> CodeMode:
    return CodeMode(
        discovery_tools=[
            _make_guide,
            GetTags(),
            Search(default_detail="detailed"),
            GetSchemas(),
        ],
        execute_description=(
            "Write Python to call tools. Inside the sandbox, `call_tool(name, params)` is the only function available.\n\n"
            "CRITICAL RULES:\n"
            "- call_tool is ASYNC — you MUST use 'await'\n"
            "- Use 'return' to get the result back\n"
            "- Do NOT use print() — it returns None\n"
            "- The sandbox supports top-level 'await' and 'return'\n\n"
            "Example to create a conference:\n"
            "  return await call_tool('create_conference', {'topic': 'My Meeting', 'mode': 'PxP'})"
        ),
    )
