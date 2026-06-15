"""On-device scheduling for the Samsung DPLUG protocol (Get/Set/DeleteSchedule).

Schedules live ON the unit: they run off the module's own (UTC) clock and fire
even while nothing is connected. Reverse-engineered from the official app
(``com.samsung.rac`` ``*ScheduleRequest``/``*ScheduleResponse``).

Wire format (single-line XML, ``\\r\\n`` terminated):

* Get:    ``<Request Type="GetSchedule" DUID="..."/>``
* Delete: ``<Request Type="DeleteSchedule" ScheduleID="..."/>`` (no DUID)
* Set::

    <Request Type="SetSchedule">
      <ScheduleInfo [ScheduleID=".."] Type="Once|EveryDay|EveryWeek"
                    Time="HH:MM" [DaySelection="Mon:Tue:.."] Activate="On|Off">
        <Control DUID=".."><Attr ID="AC_FUN_POWER" Value="On"/></Control>
      </ScheduleInfo>
    </Request>

Key subtleties (all faithfully reproduced below):

* ``Time`` is in **UTC** (the module's clock). The app converts local->UTC on
  write and UTC->local on read, using the phone's timezone; we take a ``tzinfo``.
* ``DaySelection`` is a ``:``-joined list of ``Sun Mon Tue Wed Thu Fri Sat``,
  backed by a bitmask (Sat=1 .. Sun=64). It is written only for ``Once`` and
  ``EveryWeek``.
* When the UTC conversion crosses midnight, the day bitmask is rotated (with
  Sun<->Sat wrap) so the schedule stays on the correct UTC day.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

# Day bits, exactly as the app's DaySelection.
SAT, FRI, THU, WED, TUE, MON, SUN = 1, 2, 4, 8, 16, 32, 64
EVERYDAY = 127
WEEKDAYS = MON | TUE | WED | THU | FRI  # 62

# Output order and names, matching DaySelection.toString().
_BIT_ORDER = [(SUN, "Sun"), (MON, "Mon"), (TUE, "Tue"), (WED, "Wed"), (THU, "Thu"), (FRI, "Fri"), (SAT, "Sat")]
_NAME_TO_BIT = {name: bit for bit, name in _BIT_ORDER}

# Map device day bits to/from Python weekday() (Mon=0 .. Sun=6).
_BIT_TO_PY = {MON: 0, TUE: 1, WED: 2, THU: 3, FRI: 4, SAT: 5, SUN: 6}
_PY_TO_BIT = {v: k for k, v in _BIT_TO_PY.items()}

# Schedule repetition types present on the wire.
ONCE = "Once"
EVERYDAY_TYPE = "EveryDay"
EVERYWEEK = "EveryWeek"


def mask_to_names(mask: int) -> str:
    """Render a day bitmask as the wire ``DaySelection`` string (may be empty)."""
    return ":".join(name for bit, name in _BIT_ORDER if mask & bit)


def names_to_mask(text: str | None) -> int:
    """Parse a wire ``DaySelection`` string back into a bitmask."""
    mask = 0
    for part in (text or "").split(":"):
        bit = _NAME_TO_BIT.get(part.strip())
        if bit:
            mask |= bit
    return mask


def mask_to_weekdays(mask: int) -> set[int]:
    """Bitmask -> set of Python weekday()s (Mon=0 .. Sun=6)."""
    return {_BIT_TO_PY[bit] for bit, _ in _BIT_ORDER if mask & bit}


def weekdays_to_mask(weekdays) -> int:
    """Set/iterable of Python weekday()s (Mon=0 .. Sun=6) -> bitmask."""
    mask = 0
    for wd in weekdays:
        mask |= _PY_TO_BIT[wd % 7]
    return mask


def shift_left(mask: int) -> int:
    """Rotate every day one earlier (Sat<-Sun wraps to Sat), as the app does."""
    sun = mask & SUN
    mask = (mask << 1) & EVERYDAY
    if sun:
        mask |= SAT
    return mask


def shift_right(mask: int) -> int:
    """Rotate every day one later (Sun<-Sat wraps to Sun), as the app does."""
    sat = mask & SAT
    mask = (mask >> 1) & EVERYDAY
    if sat:
        mask |= SUN
    return mask


@dataclass
class Schedule:
    """A single on-device schedule, in *local* terms (the user's timezone).

    ``attrs`` is the action applied when it fires, e.g. ``{"AC_FUN_POWER": "On"}``.
    The official app only ever schedules power on/off, but the protocol (and this
    library) accept any controllable attribute.
    """

    schedule_id: str = ""
    hour: int = 0  # local hour (0-23)
    minute: int = 0  # local minute
    repeat: str = ONCE  # ONCE | EVERYDAY_TYPE | EVERYWEEK
    days: int = 0  # local-day bitmask (only meaningful for ONCE/EVERYWEEK)
    enabled: bool = True  # maps to Activate On/Off
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def power(self) -> str | None:
        """Convenience: the AC_FUN_POWER action (``"On"``/``"Off"``) if any."""
        return self.attrs.get("AC_FUN_POWER")

    @property
    def weekdays(self) -> set[int]:
        """Local repetition days as Python weekday()s (Mon=0 .. Sun=6)."""
        return mask_to_weekdays(self.days)

    @property
    def day_names(self) -> list[str]:
        """Local repetition days as short names (``["Mon", "Tue", ...]``)."""
        return [name for bit, name in _BIT_ORDER if self.days & bit]


def _now_in(tz: datetime.tzinfo, now: datetime.datetime | None) -> datetime.datetime:
    if now is None:
        now = datetime.datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    return now.replace(second=0, microsecond=0)


def _local_to_wire(hour: int, minute: int, mask: int, tz, now) -> tuple[int, int, int]:
    """Local (hour, minute, day-mask) -> UTC (hour, minute, day-mask).

    Mirrors SetScheduleRequest.toXml(): time goes out in UTC and, if the
    conversion crosses midnight, the day bitmask is rotated to the UTC day.
    """
    ref = _now_in(tz, now)
    local_dt = ref.replace(hour=hour, minute=minute)
    offset = local_dt.utcoffset() or datetime.timedelta(0)
    utc_wall = local_dt - offset  # same tz repr, fields now hold the UTC clock
    if local_dt.weekday() != utc_wall.weekday():
        mask = shift_left(mask) if offset > datetime.timedelta(0) else shift_right(mask)
    return utc_wall.hour, utc_wall.minute, mask


def _wire_to_local(hour: int, minute: int, mask: int, tz, now) -> tuple[int, int, int]:
    """UTC (hour, minute, day-mask) -> local, reversing _local_to_wire."""
    ref = _now_in(tz, now)
    base = ref.replace(hour=hour, minute=minute)  # fields hold the UTC clock
    offset = base.utcoffset() or datetime.timedelta(0)
    local_wall = base + offset
    if base.weekday() != local_wall.weekday():
        mask = shift_left(mask) if offset < datetime.timedelta(0) else shift_right(mask)
    return local_wall.hour, local_wall.minute, mask


# -- request builders --------------------------------------------------------

def build_get_schedule(duid: str) -> str:
    return f'<Request Type="GetSchedule" DUID={quoteattr(duid)}/>'


def build_delete_schedule(schedule_id: str) -> str:
    return f'<Request Type="DeleteSchedule" ScheduleID={quoteattr(schedule_id)}/>'


def build_set_schedule(
    sched: Schedule,
    duid: str,
    tz: datetime.tzinfo = datetime.timezone.utc,
    now: datetime.datetime | None = None,
) -> str:
    """Serialise a Schedule to a SetSchedule request (creates, or edits when
    ``schedule_id`` is set). ``tz`` is the local timezone the hour/minute and
    days are expressed in; it is converted to the device's UTC clock."""
    hour, minute, mask = _local_to_wire(sched.hour, sched.minute, sched.days, tz, now)

    attrs = f' Type={quoteattr(sched.repeat)} Time={quoteattr(f"{hour:02d}:{minute:02d}")}'
    if sched.schedule_id:
        attrs = f" ScheduleID={quoteattr(sched.schedule_id)}" + attrs
    if sched.repeat in (ONCE, EVERYWEEK) and mask:
        attrs += f" DaySelection={quoteattr(mask_to_names(mask))}"
    attrs += f' Activate={quoteattr("On" if sched.enabled else "Off")}'

    inner = "".join(
        f"<Attr ID={quoteattr(k)} Value={quoteattr(v)}/>" for k, v in sched.attrs.items()
    )
    return (
        f'<Request Type="SetSchedule"><ScheduleInfo{attrs}>'
        f"<Control DUID={quoteattr(duid)}>{inner}</Control>"
        f"</ScheduleInfo></Request>"
    )


# -- response parser ---------------------------------------------------------

def parse_schedules(
    line: str,
    tz: datetime.tzinfo = datetime.timezone.utc,
    now: datetime.datetime | None = None,
) -> list[Schedule]:
    """Parse a GetSchedule response into Schedules in local (``tz``) terms."""
    out: list[Schedule] = []
    try:
        root = ET.fromstring(line.strip())
    except ET.ParseError:
        return out
    for si in root.iter("ScheduleInfo"):
        repeat = si.get("Type") or ONCE
        mask = names_to_mask(si.get("DaySelection"))
        hour = minute = 0
        time_str = si.get("Time")
        if time_str and ":" in time_str:
            try:
                uh, um = (int(x) for x in time_str.split(":", 1))
                hour, minute, mask = _wire_to_local(uh, um, mask, tz, now)
            except ValueError:
                pass
        attrs = {a.get("ID"): a.get("Value") for a in si.iter("Attr") if a.get("ID")}
        out.append(
            Schedule(
                schedule_id=si.get("ScheduleID") or "",
                hour=hour,
                minute=minute,
                repeat=repeat,
                days=mask,
                enabled=(si.get("Activate") != "Off"),
                attrs=attrs,
            )
        )
    return out
