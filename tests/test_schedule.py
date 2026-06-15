"""Tests for on-device schedule encoding/decoding (UTC + day-shift)."""
import datetime
import re

from samsung_dplug import schedule as s
from samsung_dplug.schedule import Schedule

UTC = datetime.timezone.utc
PLUS2 = datetime.timezone(datetime.timedelta(hours=2))  # e.g. CEST
MINUS5 = datetime.timezone(datetime.timedelta(hours=-5))  # e.g. EST
# A fixed reference instant so conversions are deterministic (a Wednesday).
NOW = datetime.datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def _time_attr(xml):
    return re.search(r'Time="([^"]*)"', xml).group(1)


def _days_attr(xml):
    m = re.search(r'DaySelection="([^"]*)"', xml)
    return m.group(1) if m else None


def test_mask_roundtrip_names():
    assert s.mask_to_names(s.MON | s.WED | s.FRI) == "Mon:Wed:Fri"
    assert s.names_to_mask("Mon:Wed:Fri") == s.MON | s.WED | s.FRI
    assert s.mask_to_names(s.EVERYDAY) == "Sun:Mon:Tue:Wed:Thu:Fri:Sat"
    assert s.names_to_mask("") == 0


def test_weekday_mapping():
    # Python weekday(): Mon=0 .. Sun=6
    assert s.weekdays_to_mask({0}) == s.MON
    assert s.weekdays_to_mask({6}) == s.SUN
    assert s.mask_to_weekdays(s.WEEKDAYS) == {0, 1, 2, 3, 4}


def test_shift_helpers_are_inverses():
    for bit in (s.SAT, s.SUN, s.MON, s.WED):
        assert s.shift_right(s.shift_left(bit)) == bit
        assert s.shift_left(s.shift_right(bit)) == bit
    # Sun wraps to Sat on shift_left; Sat wraps to Sun on shift_right.
    assert s.shift_left(s.SUN) == s.SAT
    assert s.shift_right(s.SAT) == s.SUN
    # shift_left moves each day one earlier: Mon -> Sun
    assert s.shift_left(s.MON) == s.SUN


def test_time_goes_out_in_utc():
    sched = Schedule(hour=8, minute=30, repeat=s.EVERYDAY_TYPE, attrs={"AC_FUN_POWER": "On"})
    xml = s.build_set_schedule(sched, "DUID1", PLUS2, NOW)
    assert _time_attr(xml) == "06:30"  # 08:30 local (+2) -> 06:30 UTC
    assert "EveryDay" in xml and _days_attr(xml) is None  # no DaySelection for EveryDay


def test_set_schedule_shape_and_power():
    sched = Schedule(
        schedule_id="0", hour=7, minute=0, repeat=s.EVERYWEEK,
        days=s.MON | s.TUE, enabled=True, attrs={"AC_FUN_POWER": "Off"},
    )
    xml = s.build_set_schedule(sched, "F8042E3F89A6", UTC, NOW)
    assert 'Type="SetSchedule"' in xml
    assert 'ScheduleID="0"' in xml
    assert 'Activate="On"' in xml
    assert '<Control DUID="F8042E3F89A6">' in xml
    assert '<Attr ID="AC_FUN_POWER" Value="Off"/>' in xml
    assert _days_attr(xml) == "Mon:Tue"  # no offset -> no shift


def test_day_shift_forward_when_utc_crosses_midnight_positive_offset():
    # 00:30 local Monday at +2 -> 22:30 UTC Sunday; mask must move Mon -> Sun.
    sched = Schedule(hour=0, minute=30, repeat=s.EVERYWEEK, days=s.MON,
                     attrs={"AC_FUN_POWER": "On"})
    xml = s.build_set_schedule(sched, "D", PLUS2, NOW)
    assert _time_attr(xml) == "22:30"
    assert _days_attr(xml) == "Sun"


def test_day_shift_negative_offset():
    # 23:30 local at -5 -> 04:30 UTC next day; Mon -> Tue.
    sched = Schedule(hour=23, minute=30, repeat=s.EVERYWEEK, days=s.MON,
                     attrs={"AC_FUN_POWER": "On"})
    xml = s.build_set_schedule(sched, "D", MINUS5, NOW)
    assert _time_attr(xml) == "04:30"
    assert _days_attr(xml) == "Tue"


def _resp(time_utc, days=None, sid="0", power="On", typ="EveryWeek", activate="On"):
    day_attr = f' DaySelection="{days}"' if days else ""
    return (
        f'<Response Type="GetSchedule" Status="Okay" DUID="D">'
        f'<ScheduleInfo Type="{typ}" Time="{time_utc}"{day_attr} ScheduleID="{sid}" Activate="{activate}">'
        f'<Attr ID="AC_FUN_POWER" Value="{power}"/></ScheduleInfo></Response>'
    )


def test_parse_converts_utc_to_local():
    scheds = s.parse_schedules(_resp("06:30", "Mon:Tue"), PLUS2, NOW)
    assert len(scheds) == 1
    sc = scheds[0]
    assert (sc.hour, sc.minute) == (8, 30)
    assert sc.days == s.MON | s.TUE
    assert sc.power == "On"
    assert sc.enabled is True
    assert sc.schedule_id == "0"


def test_parse_activate_off():
    scheds = s.parse_schedules(_resp("06:30", "Mon", activate="Off"), PLUS2, NOW)
    assert scheds[0].enabled is False


def test_roundtrip_every_offset_and_day():
    for tz in (UTC, PLUS2, MINUS5):
        for wd_bit in (s.MON, s.TUE, s.WED, s.THU, s.FRI, s.SAT, s.SUN):
            for hour in (0, 6, 12, 23):
                orig = Schedule(hour=hour, minute=15, repeat=s.EVERYWEEK,
                                days=wd_bit, attrs={"AC_FUN_POWER": "On"})
                xml = s.build_set_schedule(orig, "D", tz, NOW)
                # Build a fake response from the request's wire values and parse back.
                wire_time = _time_attr(xml)
                wire_days = _days_attr(xml)
                back = s.parse_schedules(_resp(wire_time, wire_days), tz, NOW)[0]
                assert (back.hour, back.minute) == (hour, 15), (tz, wd_bit, hour)
                assert back.days == wd_bit, (tz, wd_bit, hour)


def test_parse_multiple_and_garbage():
    assert s.parse_schedules("not xml", UTC, NOW) == []
    two = (
        '<Response Type="GetSchedule" Status="Okay" DUID="D">'
        '<ScheduleInfo Type="Once" Time="05:00" DaySelection="Mon" ScheduleID="0" Activate="On">'
        '<Attr ID="AC_FUN_POWER" Value="On"/></ScheduleInfo>'
        '<ScheduleInfo Type="EveryDay" Time="20:00" ScheduleID="1" Activate="On">'
        '<Attr ID="AC_FUN_POWER" Value="Off"/></ScheduleInfo></Response>'
    )
    scheds = s.parse_schedules(two, UTC, NOW)
    assert [sc.schedule_id for sc in scheds] == ["0", "1"]
    assert scheds[1].repeat == "EveryDay" and scheds[1].power == "Off"
