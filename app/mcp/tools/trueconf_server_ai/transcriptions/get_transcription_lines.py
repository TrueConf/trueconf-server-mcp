from typing import Any

from app._client_api._trueconf_server_ai.models import TranscriptionLinesFilters, TranscriptionLinesOutput
from app.mcp import mcp
from app.mcp.auth.trueconf_server_ai import sai_request


@mcp.tool(name="get_transcription_lines", tags={"transcriptions", "read"})
async def get_transcription_lines(
    transcription_id: int,
    page: int | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Read the actual transcript text: timestamped speaker lines.

    Each line has start_time/end_time (seconds), call_id (speaker), and
    line (text). Without filters the server returns all lines of the
    transcription. language requests translated lines when available.

    Args:
        transcription_id: Transcription id from list_transcriptions
        page: Page number (1-based)
        language: Line language filter (e.g. 'ru', 'en')
    """
    params = TranscriptionLinesFilters(page=page, language=language).model_dump(exclude_none=True)
    raw = await sai_request(
        "GET",
        f"/api/user/v1/transcriptions/{transcription_id}/lines",
        params=params,
    )
    if "error" in raw:
        return raw
    return TranscriptionLinesOutput.model_validate(raw).model_dump(exclude_none=True)
