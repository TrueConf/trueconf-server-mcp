# ── Import all tool modules to trigger @mcp.tool() registration ────────
from app.mcp.tools.trueconf_server.conferences import (  # noqa: F401
    add_invitation,
    # ── Admin ──
    calculate_conferences,
    create_conference,
    delete_conference,
    get_conference,
    get_conference_calendars,
    get_conference_ics,
    get_conference_me,
    get_conference_owner,
    # ── Participants & Roles ──
    get_conference_participants,
    # ── Translations ──
    get_conference_translations,
    # ── Links & Calendar ──
    get_deeplinks,
    get_invitation,
    get_recording,
    get_shared_links,
    invite_participants,
    join_conference,
    # ── Core CRUD ──
    list_conferences,
    # ── Invitations ──
    list_invitations,
    # ── Recordings ──
    list_recordings,
    # ── Notifications & Registration ──
    notify_conference,
    pause_recording,
    register_for_conference,
    remove_invitation,
    # ── Lifecycle ──
    run_conference,
    start_recording,
    stop_conference,
    stop_recording,
    update_conference,
    update_invitation,
)
