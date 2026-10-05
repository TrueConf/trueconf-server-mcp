"""Tests for app._client_api._trueconf_server_ai.models."""

from app._client_api._trueconf_server_ai.models import (
    AiTokenPair,
    TranscriptionLinesFilters,
    TranscriptionListFilters,
)


def test_token_pair_parses_sai_response_fields():
    data = {
        "access_token": "a",
        "access_token_expires_at": "2026-10-02T23:30:17+03:00",
        "refresh_token": "r",
        "refresh_token_expires_at": "2026-10-31T23:30:17+03:00",
    }
    pair = AiTokenPair.model_validate(data)
    assert pair.access_token == "a"
    assert pair.refresh_token == "r"
    assert pair.access_token_expires_at is not None


def test_list_filters_dump_excludes_none():
    filters = TranscriptionListFilters(page=2, page_size=10, search="test")
    assert filters.model_dump(exclude_none=True) == {
        "page": 2,
        "page_size": 10,
        "search": "test",
    }


def test_list_filters_conference_id():
    filters = TranscriptionListFilters(conference_id="8663504151")
    assert filters.model_dump(exclude_none=True) == {
        "conference_id": "8663504151",
    }


def test_lines_filters_language():
    filters = TranscriptionLinesFilters(page=1, language="ru")
    assert filters.model_dump(exclude_none=True) == {"page": 1, "language": "ru"}


def test_list_filters_sort_order():
    filters = TranscriptionListFilters(sort_field="started_at", sort_order=1)
    assert filters.model_dump(exclude_none=True) == {"sort_field": "started_at", "sort_order": 1}


def test_lines_filters_drop_page_size():
    # page_size is not part of the lines request schema (verified live
    # 2026-10-05) — the server silently ignores it, no pagination.
    filters = TranscriptionLinesFilters(page=1, page_size=1000, language="ru")
    assert filters.model_dump(exclude_none=True) == {"page": 1, "language": "ru"}
