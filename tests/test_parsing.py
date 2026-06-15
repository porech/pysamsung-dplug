"""Tests for the line/attribute parsers (no network)."""
import datetime

from samsung_dplug import parse_start_from
from samsung_dplug.client import SamsungAcClient
from samsung_dplug.stream import _ATTR_ANY

UTC = datetime.timezone.utc


def test_parse_start_from():
    line = '<Response Type="AuthToken" Status="Okay" StartFrom="2026-06-17/09:30:00"/>'
    dt = parse_start_from(line)
    assert dt == datetime.datetime(2026, 6, 17, 9, 30, 0, tzinfo=UTC)


def test_parse_start_from_missing_or_bad():
    assert parse_start_from('<Response Type="AuthToken" Status="Okay"/>') is None
    assert parse_start_from('StartFrom="not-a-date"') is None


def test_parse_state_device_state_attrs():
    # DeviceState attrs carry ID/Type/Value.
    line = (
        '<Response Type="DeviceState" Status="Okay">'
        '<Attr ID="AC_FUN_POWER" Type="RW" Value="On"/>'
        '<Attr ID="AC_FUN_TEMPSET" Type="RW" Value="24"/></Response>'
    )
    state = SamsungAcClient._parse_state(line)
    assert state["AC_FUN_POWER"] == "On"
    assert state["AC_FUN_TEMPSET"] == "24"


def test_attr_any_matches_both_state_and_push_shapes():
    # Status pushes omit the Type attribute; _ATTR_ANY must match either.
    push = '<Update Type="Status"><Attr ID="AC_FUN_OPMODE" Value="Cool"/></Update>'
    state = '<Attr ID="AC_FUN_POWER" Type="RW" Value="Off"/>'
    assert dict(_ATTR_ANY.findall(push)) == {"AC_FUN_OPMODE": "Cool"}
    assert dict(_ATTR_ANY.findall(state)) == {"AC_FUN_POWER": "Off"}
