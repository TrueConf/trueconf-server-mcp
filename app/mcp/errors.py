from __future__ import annotations

from typing import Any


def make_error(
    code: str,
    *,
    login_url: str | None = None,
    detail: str | None = None,
    message: str | None = None,
    how_to: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a consistent error dict for tool responses.

    Every error response has at least ``error`` (a stable code string) and
    ``message`` (human-readable). Auth-related errors also include
    ``login_url`` and ``how_to``. Network errors include ``detail``.
    """
    result: dict[str, Any] = {"error": code}
    if message is not None:
        result["message"] = message
    if login_url is not None:
        result["login_url"] = login_url
    if how_to is not None:
        result["how_to"] = how_to
    if detail is not None:
        result["detail"] = detail
    return result
