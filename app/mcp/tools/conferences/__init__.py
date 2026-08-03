# ── Import all tool modules to trigger @mcp.tool() registration ────────
from app.mcp.tools.conferences import (  # noqa: E402, F401
    # ── Core CRUD ──
    list_conferences,
    get_conference,
    create_conference,
    update_conference,
    delete_conference,
    # ── Lifecycle ──
    run_conference,
    stop_conference,
    join_conference,
    # ── Invitations ──
    list_invitations,
    add_invitation,
    remove_invitation,
    get_invitation,
    update_invitation,
    invite_participants,
    # ── Participants & Roles ──
    get_conference_participants,
    get_conference_owner,
    get_conference_me,
    # ── Recordings ──
    list_recordings,
    get_recording,
    start_recording,
    stop_recording,
    pause_recording,
    # ── Chat ──
    get_chat_messages,
    export_chat_messages,
    # ── Links & Calendar ──
    get_deeplinks,
    get_shared_links,
    get_conference_ics,
    get_conference_calendars,
    # ── Notifications & Registration ──
    notify_conference,
    register_for_conference,
    # ── Translations ──
    get_conference_translations,
    # ── Admin ──
    calculate_conferences,
)
