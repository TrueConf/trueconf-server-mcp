"""Unit tests for schedule helpers (schedule_utils).

Reference "now" for relative-date tests: 2026-08-10 09:00 UTC, a Monday.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.mcp.tools.trueconf_server.conferences.schedule_utils import (
    build_schedule,
    local_time_to_utc_time,
    offset_to_fixed_offset_string,
    parse_relative_date,
    parse_schedule_output_time,
    parse_utc_offset,
    resolve_partial_schedule,
    resolve_special_time_offset,
    schedule_update_is_partial,
    suggest_timezones,
)

MON = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)  # a Monday


# ── parse_utc_offset ───────────────────────────────────────────────────


def test_parse_utc_offset_positive_hours() -> None:
    assert parse_utc_offset("+3") == 180


def test_parse_utc_offset_negative_hours() -> None:
    assert parse_utc_offset("-5") == -300


def test_parse_utc_offset_bare_hours() -> None:
    assert parse_utc_offset("3") == 180


def test_parse_utc_offset_zero() -> None:
    assert parse_utc_offset("0") == 0


def test_parse_utc_offset_utc_prefix() -> None:
    assert parse_utc_offset("UTC+3") == 180


def test_parse_utc_offset_gmt_prefix() -> None:
    assert parse_utc_offset("GMT-5") == -300


def test_parse_utc_offset_hhmm() -> None:
    assert parse_utc_offset("+03:30") == 210


def test_parse_utc_offset_iana_is_none() -> None:
    assert parse_utc_offset("Europe/Moscow") is None


def test_parse_utc_offset_empty_is_none() -> None:
    assert parse_utc_offset("") is None


def test_parse_utc_offset_garbage_is_none() -> None:
    assert parse_utc_offset("телеграф") is None


# ── resolve_special_time_offset ────────────────────────────────────────


def test_resolve_iana_moscow_is_fixed_180() -> None:
    at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    assert resolve_special_time_offset("Europe/Moscow", at) == 180


def test_resolve_iana_berlin_is_dst_aware() -> None:
    summer = datetime(2026, 6, 15, tzinfo=timezone.utc)
    winter = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert resolve_special_time_offset("Europe/Berlin", summer) == 120
    assert resolve_special_time_offset("Europe/Berlin", winter) == 60


def test_resolve_numeric_offset_is_fixed() -> None:
    at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    assert resolve_special_time_offset("+3", at) == 180
    assert resolve_special_time_offset("-5", at) == -300


def test_resolve_none_uses_host_local_offset() -> None:
    at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    local_offset = at.astimezone().utcoffset()
    assert local_offset is not None
    expected = int(local_offset.total_seconds() // 60)
    assert resolve_special_time_offset(None, at) == expected


def test_resolve_unknown_timezone_raises_value_error() -> None:
    at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Unknown timezone"):
        resolve_special_time_offset("Mars/Olympus", at)


# ── suggest_timezones ──────────────────────────────────────────────────


def test_suggest_timezones_finds_moscow() -> None:
    assert "Europe/Moscow" in suggest_timezones("Moscow")


def test_suggest_timezones_finds_similar() -> None:
    hits = suggest_timezones("Moskow")
    assert hits  # fuzzy suggestion at least non-empty
    assert "Europe/Moscow" in hits


def test_suggest_timezones_unknown_returns_empty() -> None:
    assert suggest_timezones("zzzz_not_a_zone_zzzz") == []


# ── local_time_to_utc_time ─────────────────────────────────────────────


def test_local_to_utc_positive_offset() -> None:
    assert local_time_to_utc_time("13:00", 180) == "10:00"


def test_local_to_utc_negative_offset() -> None:
    assert local_time_to_utc_time("13:00", -300) == "18:00"


def test_local_to_utc_wraps_midnight() -> None:
    assert local_time_to_utc_time("00:00", 180) == "21:00"


def test_local_to_utc_pads_minutes() -> None:
    assert local_time_to_utc_time("09:30", 30) == "09:00"


# ── parse_relative_date ────────────────────────────────────────────────


def test_parse_iso_date() -> None:
    dt, tm = parse_relative_date("2026-08-17", now=MON)
    assert dt == datetime(2026, 8, 17)
    assert tm is None


def test_parse_iso_datetime() -> None:
    dt, tm = parse_relative_date("2026-08-17 13:00", now=MON)
    assert dt == datetime(2026, 8, 17, 13, 0)
    assert tm is None


def test_parse_next_monday() -> None:
    dt, _tm = parse_relative_date("next Monday", now=MON)
    assert dt == datetime(2026, 8, 17)


def test_parse_bare_monday_is_next() -> None:
    dt, _tm = parse_relative_date("Monday", now=MON)
    assert dt == datetime(2026, 8, 17)


def test_parse_this_monday_includes_today() -> None:
    dt, _tm = parse_relative_date("this Monday", now=MON)
    assert dt == datetime(2026, 8, 10)


def test_parse_this_wednesday_same_week() -> None:
    dt, _tm = parse_relative_date("this Wednesday", now=MON)
    assert dt == datetime(2026, 8, 12)


def test_parse_next_wednesday() -> None:
    # nearest upcoming Wednesday (not the following calendar week)
    dt, _tm = parse_relative_date("next Wednesday", now=MON)
    assert dt == datetime(2026, 8, 12)


def test_parse_next_today_rolls_to_next_week() -> None:
    # 'next Monday' said on a Monday → Monday next week (today excluded)
    dt, _tm = parse_relative_date("next Monday", now=MON)
    assert dt == datetime(2026, 8, 17)


def test_parse_next_friday_from_thursday() -> None:
    # regression: 'next Friday' said on Thursday resolves to tomorrow, not
    # the Friday of the following calendar week.
    thu = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
    dt, _tm = parse_relative_date("next Friday", now=thu)
    assert dt == datetime(2026, 8, 14)


def test_parse_last_monday() -> None:
    dt, _tm = parse_relative_date("last Monday", now=MON)
    assert dt == datetime(2026, 8, 3)


def test_parse_tomorrow() -> None:
    dt, _tm = parse_relative_date("tomorrow", now=MON)
    assert dt == datetime(2026, 8, 11)


def test_parse_today() -> None:
    dt, _tm = parse_relative_date("today", now=MON)
    assert dt == datetime(2026, 8, 10)


def test_parse_day_after_tomorrow() -> None:
    dt, _tm = parse_relative_date("the day after tomorrow", now=MON)
    assert dt == datetime(2026, 8, 12)


def test_parse_in_3_days() -> None:
    dt, _tm = parse_relative_date("in 3 days", now=MON)
    assert dt == datetime(2026, 8, 13)


def test_parse_in_2_weeks() -> None:
    dt, _tm = parse_relative_date("in 2 weeks", now=MON)
    assert dt == datetime(2026, 8, 24)


def test_parse_two_weeks_from_now() -> None:
    dt, _tm = parse_relative_date("two weeks from now", now=MON)
    assert dt == datetime(2026, 8, 24)


def test_parse_next_week() -> None:
    dt, _tm = parse_relative_date("next week", now=MON)
    assert dt == datetime(2026, 8, 17)


def test_parse_week_after_next() -> None:
    dt, _tm = parse_relative_date("the week after next", now=MON)
    assert dt == datetime(2026, 8, 24)


def test_parse_weekday_at_time() -> None:
    dt, tm = parse_relative_date("next Monday at 13:00", now=MON)
    assert dt == datetime(2026, 8, 17, 13, 0)
    assert tm == "13:00"


def test_parse_tomorrow_at_pm() -> None:
    dt, tm = parse_relative_date("tomorrow at 5pm", now=MON)
    assert dt == datetime(2026, 8, 11, 17, 0)
    assert tm == "17:00"


def test_parse_case_insensitive() -> None:
    dt, _tm = parse_relative_date("NEXT MONDAY", now=MON)
    assert dt == datetime(2026, 8, 17)


def test_parse_unknown_returns_none() -> None:
    assert parse_relative_date("gibberish nonsense", now=MON) == (None, None)


# ── build_schedule: once ───────────────────────────────────────────────


def test_build_schedule_once_converts_local_to_utc() -> None:
    # 13:00 +3 MSK = 10:00 UTC; ts(2026-08-17 10:00 UTC) = 1786960800
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=3600,
        days=None,
        time="13:00",
        timezone="+3",
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.type == "once"
    assert schedule.start_time == 1786960800
    assert schedule.time == "10:00"
    assert schedule.special_time_offset == 180


def test_build_schedule_once_relative_date() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="next Monday at 13:00",
        duration=3600,
        days=None,
        time=None,
        timezone="+3",
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.start_time == 1786960800
    assert schedule.time == "10:00"


def test_build_schedule_once_iso_embedded_time() -> None:
    # '2026-08-17 13:00' carries the time inside the ISO date expression.
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17 13:00",
        duration=3600,
        days=None,
        time=None,
        timezone="+3",
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.start_time == 1786960800
    assert schedule.time == "10:00"


def test_build_schedule_once_requires_timezone() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=3600,
        days=None,
        time="13:00",
        timezone=None,
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"
    assert "timezone" in error["message"]


def test_build_schedule_once_requires_date() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date=None,
        duration=None,
        days=None,
        time="13:00",
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"


def test_build_schedule_once_requires_time() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=None,
        days=None,
        time=None,
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"


def test_build_schedule_unrecognized_date_is_error() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="someday somehow",
        duration=None,
        days=None,
        time="13:00",
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"


def test_build_schedule_malformed_time_is_error() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=None,
        days=None,
        time="25:99",
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"


def test_build_schedule_unknown_timezone_is_error() -> None:
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=3600,
        days=None,
        time="13:00",
        timezone="Mars/Olympus",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_timezone"


@pytest.mark.parametrize("duration", [0, 30, 59, 86400, 100000])
def test_build_schedule_duration_out_of_range_is_error(duration: int) -> None:
    """Server accepts 60..86399s; out-of-range values (incl. the common
    minutes-instead-of-seconds mistake) are rejected client-side with a
    clear message instead of a raw upstream 400."""
    schedule, error = build_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=duration,
        days=None,
        time="13:00",
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"
    assert "60 and 86399" in error["message"]
    assert str(duration) in error["message"]


# ── build_schedule: week ───────────────────────────────────────────────


def test_build_schedule_week_with_date() -> None:
    # now=Mon 08-10, schedule_date Monday 08-10 (incl today), 10:00 +3 = 07:00 UTC
    schedule, error = build_schedule(
        schedule_type="week",
        schedule_date="2026-08-10",
        duration=3600,
        days=["monday"],
        time="10:00",
        timezone="+3",
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.type == "week"
    assert schedule.days == ["monday"]
    assert schedule.special_time_offset == 180
    # 2026-08-10 07:00 UTC
    assert schedule.start_time == int(datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc).timestamp())
    assert schedule.time == "07:00"


def test_build_schedule_week_derives_days_from_date() -> None:
    schedule, error = build_schedule(
        schedule_type="week",
        schedule_date="next Monday",
        duration=3600,
        days=None,
        time="10:00",
        timezone="+3",
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.days == ["monday"]


def test_build_schedule_week_days_only_next_occurrence() -> None:
    # now=Mon 08-10; days-only anchor excludes today → next Monday 08-17
    schedule, error = build_schedule(
        schedule_type="week",
        schedule_date=None,
        duration=3600,
        days=["monday"],
        time="10:00",
        timezone="+3",
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.start_time == int(datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc).timestamp())
    assert schedule.time == "07:00"


def test_build_schedule_week_without_days_or_date_errors() -> None:
    schedule, error = build_schedule(
        schedule_type="week",
        schedule_date=None,
        duration=3600,
        days=None,
        time="13:00",
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"


# ── build_schedule: none ───────────────────────────────────────────────


def test_build_schedule_none_bare() -> None:
    schedule, error = build_schedule(
        schedule_type="none",
        schedule_date=None,
        duration=None,
        days=None,
        time=None,
        timezone=None,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.type == "none"


def test_build_schedule_none_with_fields_errors() -> None:
    schedule, error = build_schedule(
        schedule_type="none",
        schedule_date="2026-08-17",
        duration=3600,
        days=None,
        time="13:00",
        timezone="+3",
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"


# ── offset_to_fixed_offset_string ──────────────────────────────────────


def test_offset_to_fixed_offset_string_hours() -> None:
    assert offset_to_fixed_offset_string(180) == "+3"
    assert offset_to_fixed_offset_string(-300) == "-5"


def test_offset_to_fixed_offset_string_minutes() -> None:
    assert offset_to_fixed_offset_string(210) == "+3:30"
    assert offset_to_fixed_offset_string(-330) == "-5:30"


def test_offset_to_fixed_offset_string_zero() -> None:
    assert offset_to_fixed_offset_string(0) == "0"


def test_offset_to_fixed_offset_string_roundtrip() -> None:
    for offset in (-570, -330, -60, 0, 180, 210, 540):
        assert parse_utc_offset(offset_to_fixed_offset_string(offset)) == offset


# ── parse_schedule_output_time ─────────────────────────────────────────


def test_parse_output_time_iso_z() -> None:
    assert parse_schedule_output_time("2026-08-17T10:00:00Z") == datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_parse_output_time_iso_with_offset() -> None:
    # 13:00 +03:00 = 10:00 UTC
    assert parse_schedule_output_time("2026-08-17T13:00:00+03:00") == datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_parse_output_time_naive_assumed_utc() -> None:
    assert parse_schedule_output_time("2026-08-17 10:00:00") == datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_parse_output_time_unix_string() -> None:
    assert parse_schedule_output_time("1786960800") == datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_parse_output_time_unix_number() -> None:
    assert parse_schedule_output_time(1786960800) == datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_parse_output_time_garbage_is_none() -> None:
    assert parse_schedule_output_time(None) is None
    assert parse_schedule_output_time("") is None
    assert parse_schedule_output_time("когда-нибудь") is None


# ── schedule_update_is_partial ─────────────────────────────────────────


def test_schedule_update_is_partial_complete_once_is_false() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="once",
            schedule_date="2026-08-17",
            duration=3600,
            days=None,
            time="13:00",
            timezone="+3",
        )
        is False
    )


def test_schedule_update_is_partial_embedded_time_counts() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="once",
            schedule_date="2026-08-17 13:00",
            duration=3600,
            days=None,
            time=None,
            timezone="+3",
        )
        is False
    )


def test_schedule_update_is_partial_missing_duration() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="once",
            schedule_date="2026-08-17",
            duration=None,
            days=None,
            time="13:00",
            timezone="+3",
        )
        is True
    )


def test_schedule_update_is_partial_missing_time() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="once",
            schedule_date="2026-08-17",
            duration=3600,
            days=None,
            time=None,
            timezone="+3",
        )
        is True
    )


def test_schedule_update_is_partial_once_missing_date() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="once",
            schedule_date=None,
            duration=3600,
            days=None,
            time="13:00",
            timezone="+3",
        )
        is True
    )


def test_schedule_update_is_partial_week_complete_without_date() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="week",
            schedule_date=None,
            duration=3600,
            days=["monday"],
            time="13:00",
            timezone="+3",
        )
        is False
    )


def test_schedule_update_is_partial_week_missing_days_and_date() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="week",
            schedule_date=None,
            duration=3600,
            days=None,
            time="13:00",
            timezone="+3",
        )
        is True
    )


def test_schedule_update_is_partial_missing_timezone() -> None:
    # date+time+duration complete but no timezone → partial: the offset
    # must be inherited from the current schedule's special_time_offset
    assert (
        schedule_update_is_partial(
            schedule_type="once",
            schedule_date="2026-08-17",
            duration=3600,
            days=None,
            time="13:00",
            timezone=None,
        )
        is True
    )


def test_schedule_update_is_partial_blank_timezone() -> None:
    assert (
        schedule_update_is_partial(
            schedule_type="week",
            schedule_date=None,
            duration=3600,
            days=["monday"],
            time="13:00",
            timezone="  ",
        )
        is True
    )


# ── resolve_partial_schedule (merge with current state) ────────────────

CURRENT_ONCE_OUT = {
    "type": "once",
    "start_time": "2026-08-17T10:00:00Z",
    "end_time": "2026-08-17T11:00:00Z",
    "duration": 3600,
    "special_time_offset": 180,
}
CURRENT_WEEK_OUT = {
    "type": "week",
    "start_time": "2026-08-17T10:00:00Z",
    "end_time": "2026-08-17T11:00:00Z",
    "duration": 3600,
    "days": ["monday", "wednesday"],
    "special_time_offset": 180,
}


def test_resolve_partial_schedule_time_only_once() -> None:
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date=None,
        duration=None,
        days=None,
        time="14:00",
        timezone=None,
        current=CURRENT_ONCE_OUT,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.type == "once"
    assert schedule.time == "11:00"  # 14:00 local at inherited +3
    assert schedule.duration == 3600
    assert schedule.special_time_offset == 180
    assert schedule.start_time == 1786960800 + 3600  # same date, 11:00 UTC


def test_resolve_partial_schedule_duration_only_once() -> None:
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date=None,
        duration=7200,
        days=None,
        time=None,
        timezone=None,
        current=CURRENT_ONCE_OUT,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.time == "10:00"  # inherited local 13:00 → 10:00 UTC
    assert schedule.duration == 7200
    assert schedule.start_time == 1786960800


def test_resolve_partial_schedule_week_time_only_keeps_days() -> None:
    schedule, error = resolve_partial_schedule(
        schedule_type="week",
        schedule_date=None,
        duration=None,
        days=None,
        time="15:00",
        timezone=None,
        current=CURRENT_WEEK_OUT,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.type == "week"
    assert schedule.days == ["monday", "wednesday"]
    assert schedule.time == "12:00"
    assert schedule.duration == 3600
    assert schedule.start_time == 1786960800 + 7200  # anchor date preserved


def test_resolve_partial_schedule_new_date_inherits_time_and_duration() -> None:
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date="2026-08-24",
        duration=None,
        days=None,
        time=None,
        timezone=None,
        current=CURRENT_ONCE_OUT,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.start_time == 1786960800 + 7 * 86400  # +1 week, same time
    assert schedule.duration == 3600
    assert schedule.special_time_offset == 180


def test_resolve_partial_schedule_explicit_timezone_wins() -> None:
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=3600,
        days=None,
        time="13:00",
        timezone="+4",
        current=CURRENT_ONCE_OUT,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.special_time_offset == 240
    assert schedule.time == "09:00"
    assert schedule.start_time == 1786960800 - 3600


def test_resolve_partial_schedule_timezone_only_inherited() -> None:
    # all of date/time/duration present, only timezone missing → the stored
    # offset is inherited, consistent with any other single missing field
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=3600,
        days=None,
        time="13:00",
        timezone=None,
        current=CURRENT_ONCE_OUT,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    assert schedule.special_time_offset == 180
    assert schedule.time == "10:00"
    assert schedule.start_time == 1786960800


def test_resolve_partial_schedule_no_current_keeps_standard_errors() -> None:
    for current in (None, {"type": "none"}):
        schedule, error = resolve_partial_schedule(
            schedule_type="once",
            schedule_date=None,
            duration=None,
            days=None,
            time="14:00",
            timezone=None,
            current=current,
            now=MON,
        )
        assert schedule is None
        assert error is not None
        assert error["error"] == "invalid_schedule"


def test_resolve_partial_schedule_current_missing_duration_still_errors() -> None:
    # current schedule has no duration → nothing to inherit, standard error
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date="2026-08-17",
        duration=None,
        days=None,
        time="14:00",
        timezone=None,
        current={"type": "once", "start_time": "2026-08-17T10:00:00Z"},
        now=MON,
    )
    assert schedule is None
    assert error is not None
    assert error["error"] == "invalid_schedule"
    assert "duration" in error["message"]


def test_resolve_partial_schedule_keeps_local_date_utc_minus_boundary() -> None:
    # Local 2026-08-17 01:00 at UTC+3 = 2026-08-16 22:00 UTC: the UTC date
    # (16th) is a day *behind* the local date (17th). A time-only update
    # must keep the conference on the local 17th.
    current = {
        "type": "once",
        "start_time": "2026-08-16T22:00:00Z",
        "end_time": "2026-08-16T23:00:00Z",
        "duration": 3600,
        "special_time_offset": 180,
    }
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date=None,
        duration=None,
        days=None,
        time="02:00",
        timezone=None,
        current=current,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    # 2026-08-17 02:00 local (+3) = 2026-08-16 23:00 UTC
    assert schedule.start_time == int(datetime(2026, 8, 16, 23, 0, tzinfo=timezone.utc).timestamp())
    assert schedule.time == "23:00"
    assert schedule.special_time_offset == 180


def test_resolve_partial_schedule_keeps_local_date_utc_plus_boundary() -> None:
    # Local 2026-08-16 22:00 at UTC-5 = 2026-08-17 03:00 UTC: the UTC date
    # (17th) is a day *ahead* of the local date (16th). A time-only update
    # must keep the conference on the local 16th.
    current = {
        "type": "once",
        "start_time": "2026-08-17T03:00:00Z",
        "end_time": "2026-08-17T04:00:00Z",
        "duration": 3600,
        "special_time_offset": -300,
    }
    schedule, error = resolve_partial_schedule(
        schedule_type="once",
        schedule_date=None,
        duration=None,
        days=None,
        time="23:00",
        timezone=None,
        current=current,
        now=MON,
    )
    assert error is None
    assert schedule is not None
    # 2026-08-16 23:00 local (-5) = 2026-08-17 04:00 UTC
    assert schedule.start_time == int(datetime(2026, 8, 17, 4, 0, tzinfo=timezone.utc).timestamp())
    assert schedule.time == "04:00"
    assert schedule.special_time_offset == -300
