from typing import Any

from app._client_api._trueconf_server_ai.models import TranscriptionSummaryOutput
from app.mcp import mcp
from app.mcp.auth.trueconf_server_ai import sai_request


@mcp.tool(name="get_transcription_summary", tags={"transcriptions", "read"})
async def get_transcription_summary(transcription_id: int) -> dict[str, Any]:
    """Get AI-generated summaries for a transcription.

    Returns {'summaries': [...]} — possibly empty when no summary has been
    generated yet; an empty list is a normal answer, not an error.
    """
    raw = await sai_request("GET", f"/api/user/v1/transcriptions/{transcription_id}/summary")
    if "error" in raw:
        return raw
    return TranscriptionSummaryOutput.model_validate(raw).model_dump(exclude_none=True)
