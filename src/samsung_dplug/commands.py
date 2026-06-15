"""Less-common DPLUG protocol commands, reverse-engineered from the official app.

These are best-effort: older units may not implement them (the app gates them on
firmware/option flags we cannot verify here), so callers should treat a ``Fail``
response as "unsupported".

* Power usage history (``GetPowerUsage``) and its logging controls
  (``Get``/``Set``/``ResetPowerLogging``).
* Device nickname (``ChangeNickname``).
* Region code (``Get``/``SetRegionCode``).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

_UTC = datetime.timezone.utc
# Power-usage timestamps are exchanged as UTC "yy-MM-dd HH:mm".
_PU_FMT = "%y-%m-%d %H:%M"


@dataclass
class PowerUsageEntry:
    """One bucket of power-usage history, in local (``tz``) time."""

    time: datetime.datetime  # tz-aware (local)
    power_kwh: float  # energy used in the bucket
    hours: float  # operating time in the bucket


def _to_utc(dt: datetime.datetime, tz: datetime.tzinfo) -> datetime.datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(_UTC)


def _find_attr(root: ET.Element, tag: str, attr: str) -> str | None:
    """First ``attr`` value on any ``tag`` element (root included)."""
    if root.tag == tag and root.get(attr) is not None:
        return root.get(attr)
    for el in root.iter(tag):
        if el.get(attr) is not None:
            return el.get(attr)
    return None


def _float(value: str | None) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# -- power usage -------------------------------------------------------------

def build_get_power_usage(
    date_from: datetime.datetime,
    date_to: datetime.datetime,
    unit: str = "Hour",
    tz: datetime.tzinfo = _UTC,
) -> str:
    """``unit`` is "Hour" or "Day". The range is converted from ``tz`` to UTC."""
    frm = _to_utc(date_from, tz).strftime(_PU_FMT)
    to = _to_utc(date_to, tz).strftime(_PU_FMT)
    return (
        f'<Request Type="GetPowerUsage"><PowerUsage '
        f"from={quoteattr(frm)} to={quoteattr(to)} Unit={quoteattr(unit)}/></Request>"
    )


def parse_power_usage(line: str, tz: datetime.tzinfo = _UTC) -> list[PowerUsageEntry]:
    """Parse a GetPowerUsage response into entries in local (``tz``) time."""
    out: list[PowerUsageEntry] = []
    try:
        root = ET.fromstring(line.strip())
    except ET.ParseError:
        return out
    for pu in root.iter("PowerUsage"):
        date = pu.get("Date")
        if not date:  # the request-style element has from/to, not Date
            continue
        try:
            when = datetime.datetime.strptime(date, _PU_FMT).replace(tzinfo=_UTC).astimezone(tz)
        except ValueError:
            continue
        # App scales both values by 1/10.
        out.append(PowerUsageEntry(when, _float(pu.get("PowerUsage")) / 10.0, _float(pu.get("UsageTime")) / 10.0))
    return out


def build_get_power_logging_mode() -> str:
    return '<Request Type="GetPowerLoggingMode"></Request>'


def build_set_power_logging_mode(enable: bool) -> str:
    return f'<Request Type="SetPowerLoggingMode" Mode={quoteattr("Enable" if enable else "Disable")}></Request>'


def build_reset_power_logging() -> str:
    return '<Request Type="ResetPowerLogging"></Request>'


def parse_power_logging_mode(line: str) -> bool | None:
    """Return True/False for Enable/Disable, or None if absent/unsupported."""
    try:
        root = ET.fromstring(line.strip())
    except ET.ParseError:
        return None
    mode = root.get("Mode") or _find_attr(root, "PowerLoggingMode", "Mode")
    return {"Enable": True, "Disable": False}.get(mode)


# -- nickname ----------------------------------------------------------------

def build_change_nickname(duid: str, nickname: str) -> str:
    return (
        f'<Request Type="ChangeNickname"><ChangeNickname '
        f"DUID={quoteattr(duid)} Nickname={quoteattr(nickname)}/></Request>"
    )


# -- region code -------------------------------------------------------------

def build_get_region_code() -> str:
    return '<Request Type="GetRegionCode"></Request>'


def build_set_region_code(duid: str, code: str) -> str:
    return (
        f'<Request Type="SetRegionCode"><RegionCode '
        f"DUID={quoteattr(duid)} Code={quoteattr(code)}/></Request>"
    )


def parse_region_code(line: str) -> str | None:
    """Return the region code from a GetRegionCode response, or None."""
    try:
        root = ET.fromstring(line.strip())
    except ET.ParseError:
        return None
    return _find_attr(root, "RegionCode", "Code")
