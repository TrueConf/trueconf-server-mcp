from typing import Any

from app.mcp import mcp, _request
from app.mcp.errors import make_error
from app.trueconf_api.models import ConferenceInvitationUpdate

_GUEST_RENAME_403 = make_error(
    "guest_display_name_only",
    status_code=403,
    message=(
        "The server rejected the rename (403). The display name can only be "
        "changed for external guests. This is likely a registered user — "
        "their display name comes from the account and cannot be renamed via "
        "conference invitations. If this participant is a guest, the 403 may "
        "instead mean you lack permission to edit this conference."
    ),
    how_to={
        "1": (
            "Tell the user that registered users are renamed via their "
            "account, not via conference invitations"
        ),
        "2": (
            "If the participant is a guest, retry or check permissions on "
            "the conference"
        ),
    },
)


@mcp.tool(name="update_conference_guest_display_name", tags={"invitations", "write"})
async def update_invitation(
    conference_id: str,
    invitation_id: str,
    display_name: str,
) -> dict[str, Any]:
    """Rename a guest in a conference invitation list.

    Works only for external guests (invited by name/email). Registered users'
    display names come from their account and cannot be changed via conference
    invitations.

    Args:
        conference_id: Conference identifier
        invitation_id: Invitation identifier of the guest to rename
        display_name: New display name for the guest
    """
    invitation = ConferenceInvitationUpdate(display_name=display_name)
    result = await _request(
        "PATCH",
        f"conferences/{conference_id}/invitations/{invitation_id}",
        json={"invitation": invitation.model_dump(exclude_none=True)},
    )
    if result.get("status_code") == 403:
        return _GUEST_RENAME_403
    return result
