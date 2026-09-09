"""Tests for mode_utils helpers (T11)."""

from app.trueconf_api.mode_utils import (
    _resolve_access,
    _resolve_mode,
    build_guest_rights,
)
import pytest


@pytest.mark.parametrize(
    "value, expected",
    [
        ("private", "private"),
        ("public", "public"),
        ("закрытая", "private"),
        ("открытая", "public"),
        ("приватная", "private"),
        (None, None),
        ("unknown", None),
    ],
)
def test_resolve_access(value, expected):
    assert _resolve_access(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("лекция", "OxP"),
        ("lecture", "OxP"),
        ("OxP", "OxP"),
        ("все на экране", "PxP"),
        ("по ролям", "S|L"),
        ("авто", "S|L Auto"),
        # Canonical values are case-insensitive.
        ("pxp", "PxP"),
        ("PXP", "PxP"),
        ("oxp", "OxP"),
        ("s|l", "S|L"),
        ("s|l auto", "S|L Auto"),
        ("S|L AUTO", "S|L Auto"),
    ],
)
def test_resolve_mode(value, expected):
    assert _resolve_mode(value) == expected


def test_resolve_mode_unknown_raises():
    with pytest.raises(ValueError):
        _resolve_mode("unknown mode xxx")


@pytest.mark.parametrize("value", ["s", "p", "o", "a", "л"])
def test_resolve_mode_short_fragment_does_not_match_by_substring(value):
    """A fragment of a description (e.g. 's') must not resolve to a mode.

    The reverse substring direction (input is a substring of a map key)
    matched single characters: 's' → 'PxP' (via 'all on screen'),
    'p' → 'OxP' (via 'presentation'). A user/LLM passing 'S' for S|L
    silently got the gallery mode. Short/fragment input must raise
    instead of guessing.
    """
    with pytest.raises(ValueError):
        _resolve_mode(value)


def test_resolve_mode_input_containing_key_still_matches():
    """The useful direction (a full key inside a longer phrase) is kept."""
    assert _resolve_mode("my weekly lecture") == "OxP"
    assert _resolve_mode("лекция с переводом") == "OxP"


# ── build_guest_rights ──────────────────────────────────────────────────


def test_build_guest_rights_empty_returns_none() -> None:
    assert build_guest_rights(None) is None
    assert build_guest_rights([]) is None


def test_build_guest_rights_builds_deny_map() -> None:
    result = build_guest_rights(["video_send", "audio_send"])
    assert result == {"guest": {"audio_send": False, "video_send": False}}


def test_build_guest_rights_dedupes_and_sorts() -> None:
    result = build_guest_rights(["chat_send", "chat_send", "audio_send"])
    assert result == {"guest": {"audio_send": False, "chat_send": False}}


def test_build_guest_rights_unknown_key_raises() -> None:
    with pytest.raises(ValueError, match="Unknown guest right"):
        build_guest_rights(["video_send", "bogus_right"])
