from typing import Any

from app.mcp import mcp, _request
from app.trueconf_api.models import ConferenceRegistrationRequest, ConferenceRegistrationField


@mcp.tool(tags={"conference", "write"})
async def register_for_conference(
    conference_id: str,
    fields: dict[str, str] | None = None,
    send_email: bool = True,
) -> dict[str, Any]:
    """Register a participant for a webinar conference.

    Args:
        conference_id: Conference identifier
        fields: Registration field values as {field_name: value} pairs
        send_email: Whether to send confirmation email
    """
    req_fields = None
    if fields:
        req_fields = {k: ConferenceRegistrationField(value=v) for k, v in fields.items()}
    req = ConferenceRegistrationRequest(fields=req_fields, send_email=send_email)
    return await _request(
        "POST",
        f"conferences/{conference_id}/registrations",
        json=req.model_dump(exclude_none=True),
    )
