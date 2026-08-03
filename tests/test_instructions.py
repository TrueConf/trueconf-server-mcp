"""Tests for MCP server instructions consistency across discovery modes.

Guards against drift: STATIC, BM25, and CODE_MODE instructions must all
include the common general rules (e.g. "Do not invent tool names"), so that
a shared `_COMMON_GENERAL` block cannot be silently bypassed by one mode.
"""

from app.mcp.instructions import (
    BM25_INSTRUCTIONS,
    CODE_MODE_INSTRUCTIONS,
    STATIC_INSTRUCTIONS,
)


def test_static_instructions_include_do_not_invent_tool_names():
    """STATIC mode must include the 'Do not invent tool names' rule.

    All 32 tools are visible in static mode, so this rule is especially
    important here — it must not be dropped by an inlined GENERAL RULES block.
    """
    assert "Do not invent tool names" in STATIC_INSTRUCTIONS


def test_bm25_instructions_include_do_not_invent_tool_names():
    assert "Do not invent tool names" in BM25_INSTRUCTIONS


def test_code_mode_instructions_include_do_not_invent_tool_names():
    assert "Do not invent tool names" in CODE_MODE_INSTRUCTIONS


def test_static_instructions_include_ask_only_missing_info():
    """STATIC mode keeps the 'ask only for missing info' guidance."""
    assert "ask the user only for the missing information" in STATIC_INSTRUCTIONS
