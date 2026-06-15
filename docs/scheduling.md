# On-device scheduling

The unit has a **built-in scheduler**. Schedules live **on the module** and fire
off its own clock — they run even with nothing connected (no Home Assistant, no
phone, no cloud). Model them as device state you read and write, not as
client-side automations.

Reverse-engineered from the app's `*ScheduleRequest` / `*ScheduleResponse`
classes (`com.samsung.rac.dataset`).

## Requests

### Read — `GetSchedule`

```
←  <Request Type="GetSchedule" DUID="F8042E3F89A6"/>
→  <Response Type="GetSchedule" Status="Okay" DUID="…">
     <ScheduleInfo ScheduleID="0" Type="EveryWeek" Time="06:00" DaySelection="Mon:Tue:Wed:Thu:Fri" Activate="On">
       <Attr ID="AC_FUN_POWER" Value="On"/>
     </ScheduleInfo>
     …
   </Response>
```

### Create / edit — `SetSchedule`

```xml
<Request Type="SetSchedule">
  <ScheduleInfo [ScheduleID="0"] Type="Once|EveryDay|EveryWeek"
                Time="HH:MM" [DaySelection="Mon:Tue:…"] Activate="On|Off">
    <Control DUID="F8042E3F89A6">
      <Attr ID="AC_FUN_POWER" Value="On"/>   <!-- one or more Attr: the action -->
    </Control>
  </ScheduleInfo>
</Request>
```

- **`ScheduleID` present → edit** that schedule; **absent → create** a new one.
- Response: `<Response Type="SetSchedule" Status="Okay"/>` (or `Fail` + `ErrorCode`).

### Delete — `DeleteSchedule`

```
←  <Request Type="DeleteSchedule" ScheduleID="0"/>
→  <Response Type="DeleteSchedule" Status="Okay" ScheduleID="0"/>
```

`DeleteSchedule` takes **only the `ScheduleID`** — no DUID. (Get and Set both
require the DUID.)

## Fields

### `Time` is **UTC**

`Time="HH:MM"` is in the **module's UTC clock** (the same clock as
[`StartFrom`](connection-and-auth.md#startfrom--the-device-clock)). The app
converts local→UTC on write and UTC→local on read using the phone's timezone.
A client must do the same with the user's timezone — **do not** use the device's
own offset. The library takes a `tzinfo` and converts both ways.

### `Activate` is enable/disable, not the action

`Activate="On|Off"` means the schedule is **enabled or disabled** — it is *not*
what the schedule does. The actual action is the `<Attr>`(s) inside `<Control>`
(typically `AC_FUN_POWER=On|Off`, but any controllable attribute is accepted by
the protocol).

### Repetition types

On the wire only three `Type` values exist:

| `Type` | Meaning | `DaySelection`? |
|--------|---------|-----------------|
| `Once` | Fire once at the next occurrence of the time. | Yes (the target day). |
| `EveryDay` | Every day at `Time`. | No. |
| `EveryWeek` | Weekly, on the selected days. | Yes. |

> The app also shows a **`WeekDays`** option, but that is **UI only**: on write
> it becomes `EveryWeek` + Mon–Fri; on read, `EveryWeek` with the Mon–Fri mask
> (62) is re-labelled `WeekDays`. The wire never carries `WeekDays`.

### `DaySelection` bitmask

`DaySelection` is a `:`-joined list of day names. Internally it is a bitmask
(this exact assignment matters for the day-shift below):

| Day | `Sun` | `Mon` | `Tue` | `Wed` | `Thu` | `Fri` | `Sat` |
|-----|------:|------:|------:|------:|------:|------:|------:|
| Bit |   64  |   32  |   16  |    8  |    4  |    2  |    1  |

- `EVERYDAY = 127`, weekdays (Mon–Fri) `= 62`.
- Output order is `Sun Mon Tue Wed Thu Fri Sat`, joined with `:`
  (e.g. `Mon:Tue:Wed`).

### The midnight day-shift quirk

Because `Time` is stored in UTC, converting a local time to UTC can **cross
midnight** and change the weekday. When it does, the **day bitmask is rotated**
(with `Sun↔Sat` wrap) so the schedule still fires on the intended UTC day:

- local→UTC and the day moved **earlier** (negative offset / went to previous
  day) → rotate one way; **later** → the other.
- The reverse rotation is applied on read (UTC→local).

This must be replicated faithfully or weekly schedules land on the wrong day for
users far from UTC. See `shift_left` / `shift_right` and `_local_to_wire` /
`_wire_to_local`.

## What the official app schedules vs. what the protocol allows

- **Official app:** only `AC_FUN_POWER` = `On`/`Off`. Never temperature, mode, or
  fan via a schedule.
- **Protocol / this library:** the `<Attr>` is generic — any controllable
  attribute (or several) can be scheduled. We keep this general because it is
  testable and costs nothing; clients may choose to expose only power on/off
  (as the HA integration does) while leaving the door open.

## Library mapping

`Schedule` is expressed in **local** terms; the builders/parsers do the UTC and
day-shift conversion given a `tzinfo`:

```python
from zoneinfo import ZoneInfo
from samsung_dplug import Schedule, EVERYWEEK, weekdays_to_mask

tz = ZoneInfo("Europe/Rome")
await client.async_get_schedules(tz=tz)              # -> list[Schedule], local time
await client.async_set_schedule(
    Schedule(hour=7, minute=0, repeat=EVERYWEEK,
             days=weekdays_to_mask(range(5)),         # Mon–Fri (Python weekday(): Mon=0)
             attrs={"AC_FUN_POWER": "On"}),
    tz=tz,
)
await client.async_delete_schedule("0")
```

Helpers: `mask_to_names` / `names_to_mask`, `mask_to_weekdays` /
`weekdays_to_mask`, and the constants `ONCE`, `EVERYDAY_TYPE`, `EVERYWEEK`.

---
*Code: [`schedule.py`](../src/samsung_dplug/schedule.py).*
