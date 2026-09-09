# ── Conference mode & access mappings ───────────────────────────────────

from typing import Literal

ConferenceMode = Literal["PxP", "OxP", "S|L", "S|L Auto"]
ConferenceAccess = Literal["private", "public"]

_MODE_MAP: dict[str, str] = {
    "all on screen": "PxP",
    "gallery": "PxP",
    "grid": "PxP",
    "video lecture": "OxP",
    "lecture": "OxP",
    "presentation": "OxP",
    "role-based": "S|L",
    "role based": "S|L",
    "speaker and listener": "S|L",
    "auto": "S|L Auto",
    "auto role": "S|L Auto",
    "все на экране": "PxP",
    "галерея": "PxP",
    "сетка": "PxP",
    "видеолекция": "OxP",
    "лекция": "OxP",
    "презентация": "OxP",
    "по ролям": "S|L",
    "роли": "S|L",
    "авто": "S|L Auto",
    "автоматически": "S|L Auto",
}

_ACCESS_MAP: dict[str, str] = {
    "private": "private",
    "public": "public",
    "закрытая": "private",
    "открытая": "public",
    "приватная": "private",
}


def _resolve_access(value: str | None) -> ConferenceAccess | None:
    """Map natural language or exact value to ConferenceAccess.

    Returns 'private' or 'public' for known values (incl. Russian), None for
    None/unknown. Callers can default None to 'private' where appropriate.
    """
    if value is None:
        return None
    lower = value.lower().strip()
    return _ACCESS_MAP.get(lower)  # type: ignore[return-value]


_CANONICAL_MODES: dict[str, str] = {
    "PXP": "PxP",
    "OXP": "OxP",
    "S|L": "S|L",
    "S|L AUTO": "S|L Auto",
}


GUEST_RIGHTS: frozenset[str] = frozenset(
    {
        "audio_rcv",
        "audio_send",
        "chat_rcv",
        "chat_send",
        "desktop_sharing",
        "file_transfer_rcv",
        "file_transfer_send",
        "recording",
        "remote_desktop_control",
        "slide_show_rcv",
        "slide_show_send",
        "video_rcv",
        "video_send",
        "white_board_rcv",
        "white_board_send",
    }
)


def build_guest_rights(
    guest_rights: list[str] | None,
) -> dict[str, dict[str, bool]] | None:
    """Build ``rights`` for a conference with guests enabled.

    OpenAPI defines ``rights`` only as a generic ``{role: {permission:
    bool}}`` object without an enumerated vocabulary. The actual guest
    permission keys come from the TrueConf runtime (see GUEST_RIGHTS).

    Server semantics: with ``access: public`` guests are enabled and every
    permission defaults to ``true``; a permission is disabled only by an
    explicit ``false``. So ``guest_rights`` is a *deny* list — the
    capabilities to revoke.

    Returns a ``{"guest": {perm: False, ...}}`` map suitable for the
    request body, or ``None`` when nothing restricts the granted defaults.
    Raises ValueError listing the invalid keys.
    """
    if not guest_rights:
        return None
    unknown = [k for k in guest_rights if k not in GUEST_RIGHTS]
    if unknown:
        valid = ", ".join(sorted(GUEST_RIGHTS))
        raise ValueError(
            f"Unknown guest right(s): {', '.join(unknown)}. Valid keys: {valid}."
        )
    return {"guest": {k: False for k in sorted(set(guest_rights))}}


def _resolve_mode(value: str) -> str:
    """Map natural language or exact value to ConferenceMode.

    Matching: canonical (case-insensitive) → exact description → the
    description appearing *inside* the input ("my weekly lecture"). A
    fragment of a description ("s", "screen") never matches — better a
    ValueError listing valid values than a wrong mode.
    """
    upper = value.upper().strip()
    if upper in _CANONICAL_MODES:
        return _CANONICAL_MODES[upper]
    lower = value.lower().strip()
    if lower in _MODE_MAP:
        return _MODE_MAP[lower]
    for key, mode in _MODE_MAP.items():
        if key in lower:
            return mode
    valid = ", ".join(f"'{v}'" for v in ("PxP", "OxP", "S|L", "S|L Auto"))
    raise ValueError(
        f"Неизвестный режим '{value}'. Допустимые значения: {valid}. "
        f"Или используйте описания: 'все на экране', 'лекция', 'по ролям', 'авто'."
    )
