# Other commands

Beyond [state & control](state-and-control.md) and [scheduling](scheduling.md),
the protocol has a handful of less-common commands, all decoded from the app.
Older units may not implement every one — treat a `Status="Fail"` as
"unsupported on this unit" rather than an error. Gate on
[`OPTIONCODE`](capabilities.md) where a flag exists (e.g. power usage needs the
`POWER_CONSUMPTION_TYPE` bit).

## Firmware versions — `GetSWInfo`

```
←  <Request Type="GetSWInfo" DUID="F8042E3F89A6"></Request>
→  <Response Type="GetSWInfo" …><SWInfo Version="…"/><PannelInfo Version="…"/><OutDoorInfo Version="…"/></Response>
```

Returns three versions: indoor software (`SWInfo`), the panel (`PannelInfo` —
spelled with two n's on the wire), and the outdoor unit (`OutDoorInfo`).
Library: `async_get_sw_info()` → `{"sw":…, "panel":…, "outdoor":…}`.

## Power-usage history — `GetPowerUsage`

```
←  <Request Type="GetPowerUsage"><PowerUsage from="yy-MM-dd HH:mm" to="yy-MM-dd HH:mm" Unit="Hour|Day"/></Request>
→  <Response Type="GetPowerUsage" …>
     <PowerUsage Date="yy-MM-dd HH:mm" PowerUsage="123" UsageTime="45"/> …
   </Response>
```

- `from`/`to` timestamps are **UTC**, format `yy-MM-dd HH:mm` (two-digit year).
  Convert from the user's timezone.
- `Unit` is `Hour` or `Day` (bucket granularity).
- Each result `<PowerUsage Date=… PowerUsage=… UsageTime=…/>` is one bucket
  (the request-style element with `from`/`to` and no `Date` is echoed — skip it).
- **Both `PowerUsage` and `UsageTime` are scaled ×10** — divide by 10 to get
  kWh and operating hours respectively (the app does this).

Library: `async_get_power_usage(date_from, date_to, unit="Hour", tz=…)` →
`list[PowerUsageEntry]` (bucket time in local `tz`, `power_kwh`, `hours`).

### Logging controls

The unit only accumulates usage history if logging is enabled.

| Command | Wire |
|---------|------|
| Read mode | `<Request Type="GetPowerLoggingMode"></Request>` → response with `Mode="Enable\|Disable"` |
| Set mode | `<Request Type="SetPowerLoggingMode" Mode="Enable\|Disable"></Request>` |
| Reset counters | `<Request Type="ResetPowerLogging"></Request>` |

Library: `async_get_power_logging_mode()` (→ `bool | None`),
`async_set_power_logging(enable)`, `async_reset_power_logging()`.

## Nickname — `ChangeNickname`

```
←  <Request Type="ChangeNickname"><ChangeNickname DUID="F8042E3F89A6" Nickname="Living room"/></Request>
→  <Response Type="ChangeNickname" Status="Okay"/>
```

Library: `async_set_nickname(nickname)`.

## Region code — `Get` / `SetRegionCode`

```
←  <Request Type="GetRegionCode"></Request>
→  <Response Type="GetRegionCode" …><RegionCode Code="…"/></Response>

←  <Request Type="SetRegionCode"><RegionCode DUID="F8042E3F89A6" Code="…"/></Request>
→  <Response Type="SetRegionCode" Status="Okay"/>
```

The region code affects market-specific behaviour. Library:
`async_get_region_code()` (→ `str | None`), `async_set_region_code(code)`.

---
*Code: [`commands.py`](../src/samsung_dplug/commands.py); wired up in
[`client.py`](../src/samsung_dplug/client.py) and
[`stream.py`](../src/samsung_dplug/stream.py).*
