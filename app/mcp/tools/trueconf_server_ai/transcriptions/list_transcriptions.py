from typing import Any, Literal

from app._client_api._trueconf_server_ai.models import TranscriptionListFilters, TranscriptionListOutput
from app.mcp import mcp
from app.mcp.auth.trueconf_server_ai import sai_request

# API sort_order values: 0=ascending, 1=descending (UI default: 1)
_SORT_ORDER_API: dict[str, int] = {"asc": 0, "desc": 1}


@mcp.tool(name="list_transcriptions", tags={"transcriptions", "read"})
async def list_transcriptions(
    page: int | None = None,
    page_size: int | None = None,
    search: str | None = None,
    status: int | None = None,
    conference_id: str | None = None,
    sort_field: str | None = None,
    sort_order: Literal["asc", "desc"] | None = None,
) -> dict[str, Any]:
    """List AI Server transcriptions available to the user.

    Returns paginated transcriptions recognized by the TrueConf AI Server.
    Each record includes id, display_name, conference_id, session_id,
    duration, language, status (human-readable: not recognized /
    recognizing / recognized), and transcription_url. Use
    get_transcription_lines to read the actual text. Filter by
    conference_id to find transcripts of a specific conference (the id
    from list_conferences / get_conference).

    Args:
        page: Page number (1-based)
        page_size: Records per page
        search: Free-text search in transcription names
        status: Filter by transcription status id (3=not recognized,
            6=recognizing, 8=recognized)
        conference_id: Filter by TrueConf conference id
        sort_field: One of created_at, display_name, duration, started_at
        sort_order: 'desc' (default) or 'asc'
    """
    params = TranscriptionListFilters(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        conference_id=conference_id,
        sort_field=sort_field,
        sort_order=_SORT_ORDER_API[sort_order] if sort_order is not None else None,
    ).model_dump(exclude_none=True)
    raw = await sai_request("GET", "/api/user/v1/transcriptions", params=params)
    if "error" in raw:
        return raw
    if "transcriptions" in raw or isinstance(raw, list):
        return TranscriptionListOutput.model_validate(raw).model_dump(exclude_none=True)
    return raw
