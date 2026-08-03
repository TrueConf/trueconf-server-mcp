"""Tests for mode_utils helpers (T11)."""

from app.trueconf_api.mode_utils import _resolve_access, _resolve_mode
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
