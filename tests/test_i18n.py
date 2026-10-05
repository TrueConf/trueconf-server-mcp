"""Tests for i18n language detection.

Regression tests for the malformed ``Accept-Language`` 500: a bad ``q`` value
(e.g. ``en;q=1.2.3`` or ``en;q=.``) used to raise ``ValueError`` from
``float()`` and turn ``/``, ``/success`` and ``/error`` into 500s.
"""

import pytest

from app.mcp.i18n import _parse_accept_language, detect_lang
from tests.conftest import FakeRequest

# ── _parse_accept_language: malformed q values must not raise ──────────


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        # Malformed q values — must not raise (the original 500).
        ("en;q=1.2.3", "en"),
        ("en;q=.", "en"),
        ("en;q=...", "en"),
        ("ru;q=1.2.3", "ru"),
        ("en;q=abc", "en"),
        # Valid q values keep working.
        ("en;q=0.5", "en"),
        ("en;q=1", "en"),
        ("en;q=0", "en"),
        ("en-US;q=0.8,ru;q=0.9", "ru"),
        ("ru;q=0.9,en;q=0.5", "ru"),
        ("en", "en"),
        # Out-of-range / over-precise q values are lenient but safe.
        ("en;q=2", "en"),
        ("en;q=0.9999", "en"),
        # Unsupported language with a bad q is skipped before the parse.
        ("fr;q=1.2.3,en;q=0.4", "en"),
    ],
)
def test_parse_accept_language_malformed_q(header, expected):
    assert _parse_accept_language(header) == expected


def test_parse_accept_language_no_header():
    assert _parse_accept_language(None) is None
    assert _parse_accept_language("") is None


def test_parse_accept_language_no_supported_lang():
    assert _parse_accept_language("fr,de") is None


# ── detect_lang: the seam the routes actually hit (the 500) ────────────


@pytest.mark.parametrize(
    "header",
    [
        "en;q=1.2.3",
        "en;q=.",
        "ru;q=1.2.3",
        "en;q=abc",
    ],
)
def test_detect_lang_malformed_accept_language_does_not_raise(header):
    """A malformed Accept-Language must resolve to a lang, not a 500."""
    req = FakeRequest(headers={"accept-language": header})
    # Must return a concrete language (no exception, no None).
    assert detect_lang(req) in ("ru", "en")


def test_detect_lang_query_param_wins_over_bad_header():
    req = FakeRequest(
        query_params={"lang": "en"},
        headers={"accept-language": "en;q=1.2.3"},
    )
    assert detect_lang(req) == "en"


def test_detect_lang_default_when_header_unusable():
    req = FakeRequest(headers={"accept-language": "fr;q=1.2.3"})
    # fr is unsupported, so we fall back to the default (ru).
    assert detect_lang(req) == "ru"
