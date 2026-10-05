from typing import Any

from app._client_api._trueconf_server_ai.models import TranscriptionOutput
from app.mcp import mcp
from app.mcp.auth.trueconf_server_ai import resolve_sai_base, sai_request


@mcp.tool(name="get_transcription", tags={"transcriptions", "read"})
async def get_transcription(transcription_id: int) -> dict[str, Any]:
    """Get one transcription's metadata by id.

    Returns display_name, conference_id, session_id, duration, language,
    recognition progress, and URLs: transcription_url (web UI) and
    audio_url (direct audio stream of the recording).
    """
    result = await sai_request("GET", f"/api/user/v1/transcriptions/{transcription_id}")
    if "error" not in result:
        sai_base, _ = await resolve_sai_base()
        if sai_base is not None:
            result["audio_url"] = f"{sai_base}/api/user/v1/transcriptions/{transcription_id}/audio"
        return TranscriptionOutput.model_validate(result).model_dump(exclude_none=True)
    return result
