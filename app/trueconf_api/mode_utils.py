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


def _resolve_mode(value: str) -> str:
    """Map natural language or exact value to ConferenceMode."""
    upper = value.upper().strip()
    if upper in _CANONICAL_MODES:
        return _CANONICAL_MODES[upper]
    lower = value.lower().strip()
    if lower in _MODE_MAP:
        return _MODE_MAP[lower]
    for key, mode in _MODE_MAP.items():
        if key in lower or lower in key:
            return mode
    valid = ", ".join(f"'{v}'" for v in ("PxP", "OxP", "S|L", "S|L Auto"))
    raise ValueError(
        f"Неизвестный режим '{value}'. Допустимые значения: {valid}. "
        f"Или используйте описания: 'все на экране', 'лекция', 'по ролям', 'авто'."
    )
