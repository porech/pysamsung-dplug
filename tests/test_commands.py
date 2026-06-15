"""Tests for power-usage/logging, nickname and region-code commands."""
import datetime
import re

from samsung_dplug import commands as c
from samsung_dplug.commands import PowerUsageEntry

UTC = datetime.timezone.utc
PLUS2 = datetime.timezone(datetime.timedelta(hours=2))


def _attr(xml, name):
    m = re.search(rf'{name}="([^"]*)"', xml)
    return m.group(1) if m else None


def test_get_power_usage_request_utc_and_unit():
    frm = datetime.datetime(2026, 6, 17, 8, 0)
    to = datetime.datetime(2026, 6, 17, 20, 0)
    xml = c.build_get_power_usage(frm, to, "Day", PLUS2)
    assert 'Type="GetPowerUsage"' in xml
    assert _attr(xml, "from") == "26-06-17 06:00"  # 08:00 +2 -> 06:00 UTC
    assert _attr(xml, "to") == "26-06-17 18:00"
    assert _attr(xml, "Unit") == "Day"


def test_parse_power_usage_scales_and_localizes():
    resp = (
        '<Response Type="GetPowerUsage" Status="Okay">'
        '<PowerUsage Date="26-06-17 06:00" PowerUsage="125" UsageTime="20"/>'
        '<PowerUsage Date="26-06-17 07:00" PowerUsage="0" UsageTime="0"/>'
        "</Response>"
    )
    entries = c.parse_power_usage(resp, PLUS2)
    assert len(entries) == 2
    assert entries[0].power_kwh == 12.5  # 125 / 10
    assert entries[0].hours == 2.0  # 20 / 10
    # 06:00 UTC -> 08:00 local (+2)
    assert (entries[0].time.hour, entries[0].time.tzinfo.utcoffset(None)) == (8, datetime.timedelta(hours=2))


def test_parse_power_usage_garbage():
    assert c.parse_power_usage("nonsense") == []
    # request-style element (from/to, no Date) is ignored
    assert c.parse_power_usage('<Response><PowerUsage from="a" to="b" Unit="Hour"/></Response>') == []


def test_power_logging_mode():
    assert c.build_set_power_logging_mode(True) == '<Request Type="SetPowerLoggingMode" Mode="Enable"></Request>'
    assert c.build_set_power_logging_mode(False).endswith('Mode="Disable"></Request>')
    assert c.build_reset_power_logging() == '<Request Type="ResetPowerLogging"></Request>'
    assert c.parse_power_logging_mode('<Response Type="GetPowerLoggingMode" Mode="Enable"/>') is True
    assert c.parse_power_logging_mode('<Response Type="GetPowerLoggingMode" Mode="Disable"/>') is False
    assert c.parse_power_logging_mode('<Response Type="GetPowerLoggingMode"/>') is None


def test_nickname_request():
    xml = c.build_change_nickname("F8042E3F89A6", "Living room")
    assert 'Type="ChangeNickname"' in xml
    assert 'DUID="F8042E3F89A6"' in xml
    assert 'Nickname="Living room"' in xml


def test_region_code():
    assert c.build_get_region_code() == '<Request Type="GetRegionCode"></Request>'
    xml = c.build_set_region_code("D", "EU")
    assert 'Type="SetRegionCode"' in xml and 'Code="EU"' in xml and 'DUID="D"' in xml
    resp = '<Response Type="GetRegionCode" Status="Okay"><RegionCode Code="EU"/></Response>'
    assert c.parse_region_code(resp) == "EU"
    assert c.parse_region_code("bad xml") is None


def test_quoting_escapes_specials():
    # A nickname with quotes/ampersands must stay valid XML and round-trip.
    from xml.etree import ElementTree as ET

    xml = c.build_change_nickname("D", 'A & "B"')
    assert "&amp;" in xml  # ampersand escaped
    el = ET.fromstring(xml).find("ChangeNickname")
    assert el.get("Nickname") == 'A & "B"'
