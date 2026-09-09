"""Timezone + natural-language date helpers for scheduled conferences.

Maps user-facing timezone strings (IANA names like ``Europe/Moscow`` or
numeric UTC offsets like ``+3`` / ``-5`` / ``UTC+3``) to the integer
``special_time_offset`` (UTC offset in minutes) that the TrueConf API
requires inside ``schedule``.

Also parses natural-language *English* date expressions (the LLM passes
MCP tool parameters in English) such as ``"next Monday"``, ``"this
Wednesday"``, ``"in 3 days"``, ``"two weeks from now"`` or
``"2026-08-17"`` into a concrete ``start_time``, and converts a local
wall-clock ``schedule.time`` into the UTC string the server stores
(TrueConf stores ``schedule.time`` as UTC and applies
``special_time_offset`` only for display).

Design decisions (from the grill session):
- ``+3``-style input is a *fixed* offset — no DST, no zoneinfo resolution.
- IANA names resolve through ``zoneinfo`` and are DST-aware at the
  reference instant.
- No timezone dictionary / transliteration: the LLM is expected to pass a
  proper IANA name (tool descriptions show examples). Unknown names
  produce an error with candidate suggestions for the LLM to pick from.
- Scheduled conferences need a ``timezone`` to convert the user's local
  wall-clock time to UTC; a missing ``timezone`` is an explicit error
  (the tool then tells the LLM to ask the user for a timezone or a fixed
  offset) instead of silently guessing.
- ``week`` conferences pin the offset at the first occurrence (TrueConf
  stores a single integer; DST drift across the year is an upstream
  limitation — we intentionally do NOT roll the offset between seasons).
- Relative dates ("next Monday") are resolved against the server's
  *current* time via ``datetime.now`` — the LLM never needs to know
  today's date.
"""

from __future__ import annotations

import difflib
import re
from datetime import date, datetime, timedelta, timezone as tz_mod
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import pydantic

from app.mcp.errors import make_error
from app.trueconf_api.models import ConferenceSchedule, ScheduleType

_UTC_OFFSET_RE = re.compile(
    r"^(?:(?:UTC|GMT)\s*)?(?P<sign>[+-]?)(?P<hours>\d{1,2})(?::(?P<minutes>\d{2}))?$",
    re.IGNORECASE,
)

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_WEEKDAY_INDEX = {name: i for i, name in enumerate(WEEKDAYS)}

_NUM_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_TIME_SUFFIX_RE = re.compile(
    r"(?i)\b at \s+ (\d{1,2}) \s* :? \s* (\d{2})? \s* ([ap])? \.? \s* m? \.? \s* $",
    re.VERBOSE,
)
_ISO_DATETIME_RE = re.compile(
    r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?\s*$"
)
_WEEKDAY_RE = re.compile(
    r"(?i)^\s*(?:(next|this|last)\s+)?"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*$"
)
_SHIFT_IN_RE = re.compile(r"(?i)^\s*in\s+(\S+)\s+(day|week)s?\s*$")
_SHIFT_FROM_NOW_RE = re.compile(r"(?i)^\s*(\S+)\s+(day|week)s?\s+from\s+now\s*$")
_TIME_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def parse_utc_offset(text: str) -> int | None:
    """Parse a numeric UTC offset into minutes, or None if not numeric.

    Accepts ``+3``, ``-5``, ``3``, ``UTC+3``, ``GMT-5``, ``+03:30``, ``0``.
    Returns None for anything that is not a recognisable numeric offset,
    so the caller can fall back to IANA resolution.
    """
    stripped = text.strip()
    if not stripped:
        return None
    match = _UTC_OFFSET_RE.match(stripped)
    if match is None:
        return None
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes") or 0)
    if hours > 14 or minutes > 59:
        return None
    total = hours * 60 + minutes
    if match.group("sign") == "-":
        total = -total
    return total


def suggest_timezones(query: str, limit: int = 5) -> list[str]:
    """Best-effort list of IANA names close to ``query``.

    Uses exact substring first, then fuzzy-matching against the region tail
    (e.g. 'Moscow'), then fuzzy over the whole set.
    """
    query = query.strip()
    if not query:
        return []
    q = query.lower()
    hits = [z for z in available_timezones() if q in z.lower()]
    if not hits:
        tails = {z.split("/")[-1]: z for z in available_timezones()}
        close = difflib.get_close_matches(q, list(tails), n=limit, cutoff=0.6)
        hits = [tails[tail] for tail in close]
    if not hits:
        hits = difflib.get_close_matches(
            q, list(available_timezones()), n=limit, cutoff=0.6
        )
    return hits[:limit]


def _unknown_timezone_message(text: str) -> str:
    suggestions = suggest_timezones(text)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    return (
        f"Unknown timezone '{text}'. Pass an IANA name (e.g. 'Europe/Moscow') "
        f"or a numeric UTC offset (e.g. '+3', '-5', 'UTC+3').{hint}"
    )


def resolve_special_time_offset(timezone: str | None, at: datetime) -> int:
    """Return the UTC offset in minutes for ``timezone`` at instant ``at``.

    - numeric offset (``+3``/``-5``/``UTC+3``) → fixed minutes, no DST
    - IANA name (``Europe/Moscow``) → DST-aware offset at ``at``
    - ``None``/empty → the host's local timezone offset at ``at``

    Raises ValueError with candidate suggestions for unknown names.
    """
    if timezone is None or not timezone.strip():
        offset = at.astimezone().utcoffset()
        if offset is None:
            return 0
        return int(offset.total_seconds() // 60)

    text = timezone.strip()
    parsed = parse_utc_offset(text)
    if parsed is not None:
        return parsed

    try:
        zone = ZoneInfo(text)
    except (KeyError, ValueError) as e:
        raise ValueError(_unknown_timezone_message(text)) from e

    offset = zone.utcoffset(at)
    if offset is None:
        return 0
    return int(offset.total_seconds() // 60)


def _to_hhmm(value: str) -> tuple[int, int]:
    """Split a ``"HH:MM"`` string into ``(hour, minute)``."""
    hour, minute = (int(x) for x in value.split(":"))
    return hour, minute


def local_time_to_utc_time(local_time: str, offset_minutes: int) -> str:
    """Convert a local wall-clock ``"HH:MM"`` to the UTC ``"HH:MM"``.

    The TrueConf API stores ``schedule.time`` as UTC. ``offset_minutes`` is
    the UTC offset of the conference's timezone (positive east of UTC).
    """
    hour, minute = _to_hhmm(local_time)
    total = (hour * 60 + minute - offset_minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _at_time(date_obj: date, time_of_day: str | None) -> datetime:
    hour, minute = _to_hhmm(time_of_day) if time_of_day else (0, 0)
    return datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)


def _to_int(token: str) -> int | None:
    lowered = token.lower()
    if lowered in _NUM_WORDS:
        return _NUM_WORDS[lowered]
    try:
        return int(token)
    except ValueError:
        return None


def _extract_time_suffix(text: str) -> tuple[str, str | None]:
    """Return ``(text_without_suffix, "HH:MM")`` if trailing 'at HH:MM'."""
    match = _TIME_SUFFIX_RE.search(text)
    if match is None:
        return text, None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    meridian = (match.group(3) or "").lower()
    if meridian == "p" and hour < 12:
        hour += 12
    elif meridian == "a" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return text, None
    base = text[: match.start()].strip()
    return base, f"{hour:02d}:{minute:02d}"


def parse_relative_date(
    text: str, *, now: datetime | None = None
) -> tuple[datetime | None, str | None]:
    """Parse a natural-language English date into ``(datetime, "HH:MM")``.

    ``schedule_date`` strings come from the LLM in English. Supported forms
    (case-insensitive):

    - ISO dates: ``"2026-08-17"``, ``"2026-08-17 13:00"``
    - weekdays: ``"next Monday"``, ``"this Wednesday"``, ``"Friday"``
    - relative: ``"today"``, ``"tomorrow"``, ``"the day after tomorrow"``
    - shifts: ``"in 3 days"``, ``"in 2 weeks"``, ``"two weeks from now"``
    - weeks: ``"next week"``, ``"the week after next"``
    - a trailing time: ``"next Monday at 13:00"``, ``"today at 5pm"``

    Semantics: ``this X``, ``next X`` and a bare ``X`` all mean the nearest
    upcoming occurrence of that weekday (e.g. "next Friday" said on a
    Thursday resolves to the following day); only ``this X`` may be today
    (for ``next X`` / bare ``X``, if today is ``X`` we roll to next week).
    ``last X`` is the most recent one strictly before today. Returns
    ``(None, None)`` when the expression is not recognised.
    """
    base_now = now or datetime.now(tz_mod.utc)
    base_date = base_now.date()

    base, time_of_day = _extract_time_suffix(text.strip())
    lowered = base.lower().strip()
    if not lowered:
        return None, None

    iso_match = _ISO_DATETIME_RE.match(base)
    if iso_match:
        year, month, day = (int(iso_match.group(i)) for i in (1, 2, 3))
        try:
            result = datetime(year, month, day)
        except ValueError:
            return None, None
        hour, minute = 0, 0
        if iso_match.group(4) is not None:
            hour = int(iso_match.group(4))
            minute = int(iso_match.group(5))
            if hour > 23 or minute > 59:
                return None, None
        return result.replace(hour=hour, minute=minute), time_of_day

    if lowered == "today":
        return _at_time(base_date, time_of_day), time_of_day
    if lowered == "tomorrow":
        return _at_time(base_date + timedelta(days=1), time_of_day), time_of_day
    if lowered in ("day after tomorrow", "the day after tomorrow"):
        return _at_time(base_date + timedelta(days=2), time_of_day), time_of_day
    if lowered == "next week":
        return _at_time(base_date + timedelta(days=7), time_of_day), time_of_day
    if lowered in ("week after next", "the week after next"):
        return _at_time(base_date + timedelta(days=14), time_of_day), time_of_day

    weekday_match = _WEEKDAY_RE.match(lowered)
    if weekday_match:
        modifier, weekday = weekday_match.groups()
        target = _WEEKDAY_INDEX[weekday]
        if modifier == "last":
            delta = (target - base_date.weekday()) % 7 - 7
            target_date = base_date + timedelta(days=delta)
        else:
            # 'this X', 'next X' and bare 'X' all resolve to the nearest
            # upcoming occurrence of X; only 'this X' may be today.
            delta = (target - base_date.weekday()) % 7
            if delta == 0 and modifier != "this":
                delta = 7
            target_date = base_date + timedelta(days=delta)
        return _at_time(target_date, time_of_day), time_of_day

    shift_match = _SHIFT_IN_RE.match(lowered) or _SHIFT_FROM_NOW_RE.match(lowered)
    if shift_match:
        number, unit = shift_match.groups()
        amount = _to_int(number)
        if amount is None:
            return None, None
        days = amount * (7 if unit == "week" else 1)
        return _at_time(base_date + timedelta(days=days), time_of_day), time_of_day

    return None, None


def _next_matching_date(base, weekday_indices, *, including_same) -> datetime:
    start = 0 if including_same else 1
    for offset_days in range(start, start + 7):
        candidate = base + timedelta(days=offset_days)
        if candidate.weekday() in weekday_indices:
            return candidate
    return base + timedelta(days=7)  # unreachable: covers all 7 weekdays


def build_schedule(
    *,
    schedule_type: ScheduleType,
    schedule_date: str | None,
    duration: int | None,
    days: list[str] | None,
    time: str | None,
    timezone: str | None,
    now: datetime | None = None,
) -> tuple[ConferenceSchedule | None, dict[str, Any] | None]:
    """Build a schedule from user-facing local values.

    The LLM passes the *local* wall-clock time and a natural-language date
    expression; this function converts them into the UTC ``start_time``,
    UTC ``schedule.time`` and ``special_time_offset`` the TrueConf API
    stores.

    Returns ``(schedule, None)`` on success and ``(None, error_dict)`` on
    failure. Guards these failure modes (all ``invalid_schedule`` except the
    timezone one):

    - schedule fields passed with ``type="none"``;
    - ``once`` without ``schedule_date``;
    - ``week`` without ``schedule_date`` *and* without ``days``;
    - unrecognised ``schedule_date`` expression;
    - scheduled conference without a ``time`` (or time embedded in the date);
    - scheduled conference without a ``timezone`` (needed to convert the
      local time to UTC);
    - ``schedule_duration`` outside the server's 60..86399-second range
      (catches the common "minutes instead of seconds" mistake client-side
      instead of leaking a raw upstream 400);
    - malformed ``schedule_time``;
    - invalid weekday values (pydantic);
    - unknown timezone → ``invalid_timezone`` with candidate suggestions.
    """
    has_fields = any(v is not None for v in (schedule_date, duration, days, time))
    if schedule_type == "none":
        if has_fields:
            return None, make_error(
                "invalid_schedule",
                message=(
                    "schedule_type must be 'once' or 'week' when schedule "
                    "fields are provided."
                ),
            )
        return ConferenceSchedule(type="none"), None
    if schedule_type == "once" and schedule_date is None:
        return None, make_error(
            "invalid_schedule",
            message="schedule_date is required for schedule_type='once'.",
        )
    if schedule_type == "week" and schedule_date is None and not days:
        return None, make_error(
            "invalid_schedule",
            message=(
                "schedule_days or schedule_date is required for schedule_type='week'."
            ),
        )
    if duration is None:
        return None, make_error(
            "invalid_schedule",
            message=(
                f"schedule_duration is required for schedule_type='{schedule_type}' "
                f"(server rejects scheduled conferences without it)."
            ),
        )
    if not 60 <= duration <= 86399:
        return None, make_error(
            "invalid_schedule",
            message=(
                f"schedule_duration must be between 60 and 86399 seconds "
                f"(1 minute .. 24 hours), got {duration}."
            ),
        )

    base_now = now or datetime.now(tz_mod.utc)

    parsed_dt: datetime | None = None
    parsed_time: str | None = None
    if schedule_date is not None:
        parsed_dt, parsed_time = parse_relative_date(schedule_date, now=base_now)
        if parsed_dt is None:
            return None, make_error(
                "invalid_schedule",
                message=(
                    f"Unrecognized schedule_date '{schedule_date}'. Use "
                    "'YYYY-MM-DD' or a phrase like 'next Monday', "
                    "'this Wednesday', 'tomorrow', 'in 3 days', 'next week'."
                ),
            )

    if time is None:
        time = parsed_time
    if time is None and parsed_dt is not None and (parsed_dt.hour or parsed_dt.minute):
        time = parsed_dt.strftime("%H:%M")
    if time is None:
        return None, make_error(
            "invalid_schedule",
            message=(
                f"schedule_time is required for schedule_type='{schedule_type}' "
                "(or include a time in schedule_date, e.g. 'next Monday at 13:00')."
            ),
        )
    if not _TIME_HHMM_RE.match(time):
        return None, make_error(
            "invalid_schedule",
            message=f"Invalid schedule_time '{time}'. Use 'HH:MM', e.g. '13:00'.",
        )

    if days:
        days = [str(d).lower() for d in days]
    invalid_days = [d for d in days if d not in _WEEKDAY_INDEX] if days else []
    if invalid_days:
        return None, make_error(
            "invalid_schedule",
            message=(
                f"Invalid weekday(s) {invalid_days}. One of: {', '.join(WEEKDAYS)}."
            ),
        )

    # Resolve the first-occurrence date.
    if schedule_type == "week":
        if not days and parsed_dt is not None:
            days = [WEEKDAYS[parsed_dt.weekday()]]
        if not days:
            return None, make_error(
                "invalid_schedule",
                message="schedule_days is required for schedule_type='week'.",
            )
        first = _next_matching_date(
            parsed_dt.date() if parsed_dt is not None else base_now.date(),
            [_WEEKDAY_INDEX[d] for d in days],
            including_same=parsed_dt is not None,
        )
    else:
        if parsed_dt is None:
            return None, make_error(
                "invalid_schedule",
                message="schedule_date is required for schedule_type='once'.",
            )
        first = parsed_dt.date()

    hour, minute = _to_hhmm(time)
    first_local = datetime(first.year, first.month, first.day, hour, minute)

    if not timezone or not timezone.strip():
        return None, make_error(
            "invalid_schedule",
            message=(
                f"timezone is required to convert the local schedule_time to "
                f"UTC for schedule_type='{schedule_type}'. Pass an IANA name "
                "(e.g. 'Europe/Moscow') or a fixed UTC offset (e.g. '+3', '-5')."
            ),
        )
    try:
        offset = resolve_special_time_offset(timezone, first_local)
    except ValueError as e:
        return None, make_error("invalid_timezone", message=str(e))

    aware = first_local.replace(tzinfo=tz_mod.utc) - timedelta(minutes=offset)
    start_time = int(aware.timestamp())
    utc_time = local_time_to_utc_time(time, offset)

    try:
        schedule = ConferenceSchedule(
            type=schedule_type,
            start_time=start_time,
            duration=duration,
            days=days,
            time=utc_time,
            special_time_offset=offset,
        )
    except pydantic.ValidationError as e:
        return None, make_error("invalid_schedule", detail=str(e.errors()))
    return schedule, None


def offset_to_fixed_offset_string(offset: int) -> str:
    """Format a UTC offset in minutes as a fixed-offset string.

    The result is accepted by ``parse_utc_offset`` (and therefore by
    ``resolve_special_time_offset``), so a stored ``special_time_offset``
    can be fed back into ``build_schedule`` without knowing the original
    IANA name: ``180 → '+3'``, ``-330 → '-5:30'``, ``0 → '0'``.
    """
    if offset == 0:
        return "0"
    sign = "+" if offset > 0 else "-"
    hours, minutes = divmod(abs(offset), 60)
    if minutes:
        return f"{sign}{hours}:{minutes:02d}"
    return f"{sign}{hours}"


def parse_schedule_output_time(value: Any) -> datetime | None:
    """Parse a ``ScheduleOutput`` ``start_time``/``end_time`` into aware UTC.

    The spec types the field as ``string`` without pinning a format, so this
    accepts unix seconds (a number or its string form) and ISO-8601 /
    RFC-3339 strings; naive values are assumed to be UTC. Returns None when
    the value is unparseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=tz_mod.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromtimestamp(float(text), tz=tz_mod.utc)
    except (ValueError, OverflowError, OSError):
        pass
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz_mod.utc)
    return parsed.astimezone(tz_mod.utc)


def _recover_local_time(current: dict[str, Any]) -> str | None:
    """Recover the local wall-clock ``"HH:MM"`` from a stored schedule.

    The server response keeps ``start_time`` (UTC) and
    ``special_time_offset`` (minutes) but no ``time`` field, so the local
    time is the UTC start plus the offset. For ``week`` schedules the
    anchor's time of day is used as the repeat time (TrueConf stores a
    single time/offset pair; schedules created through this tool anchor the
    first occurrence exactly at the repeat time).
    """
    start = parse_schedule_output_time(current.get("start_time"))
    offset = current.get("special_time_offset")
    if start is None or not isinstance(offset, int) or isinstance(offset, bool):
        return None
    local = start + timedelta(minutes=offset)
    return f"{local.hour:02d}:{local.minute:02d}"


def schedule_update_is_partial(
    *,
    schedule_type: ScheduleType,
    schedule_date: str | None,
    duration: int | None,
    days: list[str] | None,
    time: str | None,
    timezone: str | None,
) -> bool:
    """Whether a (re)schedule request omits fields the server requires.

    The server demands the full field set per type (``once`` — start_time,
    time, special_time_offset, duration; ``week`` — plus non-empty days),
    so a request that leaves any of them out must inherit them from the
    conference's current schedule. A time embedded in ``schedule_date``
    counts as provided. A missing (or blank) ``timezone`` also counts as
    partial for ``once``/``week`` — the offset is inherited from the
    current schedule's ``special_time_offset``.
    """
    if schedule_type == "once" and schedule_date is None:
        return True
    if schedule_type == "week" and not days and schedule_date is None:
        return True
    if duration is None:
        return True
    if time is None:
        parsed_dt, embedded = (
            parse_relative_date(schedule_date) if schedule_date else (None, None)
        )
        if embedded is None and not (
            parsed_dt is not None and (parsed_dt.hour or parsed_dt.minute)
        ):
            return True
    if schedule_type in ("once", "week") and not (timezone and timezone.strip()):
        return True
    return False


def resolve_partial_schedule(
    *,
    schedule_type: ScheduleType,
    schedule_date: str | None,
    duration: int | None,
    days: list[str] | None,
    time: str | None,
    timezone: str | None,
    current: dict[str, Any] | None,
    now: datetime | None = None,
) -> tuple[ConferenceSchedule | None, dict[str, Any] | None]:
    """``build_schedule`` with inheritance from the current schedule.

    Missing required fields (duration, time, days, first-occurrence date,
    timezone) are filled in from the conference's current server-side
    schedule, so a partial update is rebuilt into the full field set the
    server demands. ``current`` is the raw ``schedule`` object from
    ``GET /conferences/{id}`` (``conference.ScheduleOutput``); ``None`` or
    ``{"type": "none"}`` means nothing to inherit and the standard
    ``build_schedule`` required-field errors apply.
    """
    cur = current if isinstance(current, dict) else {}
    usable = cur.get("type") in ("once", "week")

    effective_duration = duration
    if effective_duration is None and usable:
        cur_duration = cur.get("duration")
        if (
            isinstance(cur_duration, int)
            and not isinstance(cur_duration, bool)
            and cur_duration > 0
        ):
            effective_duration = cur_duration

    effective_days = days
    if not effective_days and usable and cur.get("days"):
        effective_days = list(cur["days"])

    effective_time = time
    if effective_time is None:
        parsed_dt, embedded = (
            parse_relative_date(schedule_date, now=now)
            if schedule_date
            else (None, None)
        )
        # same rule as build_schedule: an ISO date like '2026-08-17 13:00'
        # carries its time in the parsed datetime, not in ``embedded``
        has_embedded = embedded is not None or (
            parsed_dt is not None and (parsed_dt.hour or parsed_dt.minute)
        )
        if not has_embedded and usable:
            effective_time = _recover_local_time(cur)

    effective_timezone = timezone
    if not effective_timezone and usable:
        cur_offset = cur.get("special_time_offset")
        if isinstance(cur_offset, int) and not isinstance(cur_offset, bool):
            effective_timezone = offset_to_fixed_offset_string(cur_offset)

    effective_date = schedule_date
    if effective_date is None and usable:
        cur_start = parse_schedule_output_time(cur.get("start_time"))
        if cur_start is not None:
            cur_offset = cur.get("special_time_offset")
            if isinstance(cur_offset, int) and not isinstance(cur_offset, bool):
                # start_time is UTC; the first-occurrence date is the *local*
                # date (start + offset) — it differs from the UTC date when
                # the local time crosses the UTC day boundary.
                cur_start = cur_start + timedelta(minutes=cur_offset)
            effective_date = cur_start.strftime("%Y-%m-%d")

    return build_schedule(
        schedule_type=schedule_type,
        schedule_date=effective_date,
        duration=effective_duration,
        days=effective_days,
        time=effective_time,
        timezone=effective_timezone,
        now=now,
    )
