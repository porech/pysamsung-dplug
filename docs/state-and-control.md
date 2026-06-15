# State & control

Once [authenticated](connection-and-auth.md), the connection exchanges three
kinds of payload: **discovery** (`DeviceList`), **state reads** (`DeviceState`),
and **commands** (`DeviceControl`). The device also pushes **unsolicited
updates** when its state changes.

## Discovering the DUID — `DeviceList`

If you don't already know the [DUID](transport.md#the-duid):

```
←  <Request Type="DeviceList"></Request>
→  <Response Type="DeviceList" …><Device DUID="F8042E3F89A6" …/></Response>
```

Take the `Device DUID="…"` attribute. (The streaming client does this
automatically right after auth when no DUID was configured.)

## Reading state — `DeviceState`

```
←  <Request Type="DeviceState" DUID="F8042E3F89A6"></Request>
→  <Response Type="DeviceState" Status="Okay"> … <Attr ID="AC_FUN_POWER" Type="RW" Value="On"/> … </Response>
```

- **DUID is mandatory** — without it: `Status="Fail" … ErrorCode="103"`.
- The response is a flat list of `<Attr ID="…" Type="RW|R" Value="…"/>` elements.
  `Type` is `RW` (writable) or `R` (read-only).
- **Read-after-write:** the state snapshot the device sends right after auth is a
  *pre-command* snapshot. After a `DeviceControl`, re-read `DeviceState` (or wait
  for a push) to observe the new value.

## Sending a command — `DeviceControl`

```
←  <Request Type="DeviceControl"><Control CommandID="cmd" DUID="F8042E3F89A6"><Attr ID="AC_FUN_POWER" Value="On" /></Control></Request>
→  <Response Type="DeviceControl" Status="Okay"/>
```

- `CommandID` is an opaque client-chosen label echoed back; any stable value
  works (the library uses `"cmd"`).
- You may include **multiple `<Attr>`** in one `<Control>` to set several
  attributes atomically.
- `Status="Okay"` means *accepted*, not necessarily *applied & observable yet* —
  re-read or await a push to confirm (see read-after-write above). The streaming
  client's `async_set(..., confirm=True)` waits for the value to appear in a push
  before returning, enabling a flicker-free pending→applied UX.

## Live updates — `Update` / `Status` pushes

On the persistent connection the device **pushes** changes as they happen
(physical remote, schedule firing, another client, etc.):

```
→  <Update Type="Status"> … <Attr ID="AC_FUN_TEMPNOW" Value="26"/> … </Update>
```

Notes for parsers:

- Push `<Attr>` carry `ID`/`Value` but **may omit `Type`** — match both shapes
  (`Attr ID="…" … Value="…"`), which is why the stream uses a looser regex than
  the `DeviceState` parser.
- `DeviceControl` acknowledgements can also carry `Attr` pairs; merge them too.
- Filter out `InvalidateAccount` updates — those are auth signals, not state.

## Attribute reference (`AC_*`)

Attributes are namespaced strings. The set below is what we have observed /
decoded; a given unit only exposes the subset its hardware and
[`OPTIONCODE`](capabilities.md) support. **Gate features on `OPTIONCODE`, not on
attribute presence** — units report attributes for features they don't actually
have.

### Writable (`RW`) — the common controls

| Attribute | Values | Meaning |
|-----------|--------|---------|
| `AC_FUN_POWER` | `On` \| `Off` | Power. |
| `AC_FUN_OPMODE` | `Cool` \| `Heat` \| `Dry` \| `Wind` \| `Auto` | Operating mode. |
| `AC_FUN_TEMPSET` | integer °C (or °F if `FAHRENHEIT` option) | Target setpoint. |
| `AC_FUN_WINDLEVEL` | `Low` \| `Mid` \| `High` \| `Auto` \| `Turbo` | Fan speed. |
| `AC_FUN_DIRECTION` | `Fixed` \| `SwingUD` \| … | Louver / swing direction. |
| `AC_FUN_COMODE` | `Off` \| `Quiet` \| `Sleep` \| `Smart` \| … | Comfort/convenience preset. |
| `AC_FUN_SLEEP` | minutes / `0` | Sleep timer. |
| `AC_ADD_AUTOCLEAN` | `On` \| `Off` | Auto-clean (dry-out) after stop. |
| `AC_ADD_SPI` | `On` \| `Off` | SPi / Virus Doctor (only if `SPI` option). |

### Read-only (`R`) — sensors & status

| Attribute | Meaning |
|-----------|---------|
| `AC_FUN_TEMPNOW` | Indoor (room) temperature. |
| `AC_OUTDOOR_TEMP` | Outdoor temperature. **Quirk: reported in °F on some units regardless of the unit setting — convert.** |
| `AC_FUN_ERROR` | `NULL` when no error, otherwise an error code. |
| `AC_FUN_ENABLE` | Capability/enable flag reported by the unit. |
| `AC_SG_WIFI`, `AC_SG_INTERNET` | `Connected` / connectivity status. |
| `AC_ADD2_OPTIONCODE` | Capability bitmask — see [Capabilities](capabilities.md). |
| `AC_ADD2_VERSION`, `AC_ADD2_PANEL_VERSION`, … | Firmware / panel versions (also via `GetSWInfo`). |
| `AC_ADD_WIFIMODE`, `AC_ADD_APMODE_END`, `AC_ADD_STARTWPS`, `AC_ADD_WPS_END` | WiFi/provisioning state — see [Provisioning](provisioning.md). |

> This table is "best known", not exhaustive. The full attribute space is large
> and partly model-specific; dump `DeviceState` on your unit to see its actual
> set. Contributions extending this table are welcome.

## Errors

Failures come back as `Status="Fail"` with an `ErrorCode`:

| `ErrorCode` | Meaning |
|-------------|---------|
| `103` | Missing/invalid DUID on a request that requires it. |
| (auth) | A `Fail` mentioning `Auth` → token rejected; re-authenticate, don't retry blindly. |

---
*Code: [`client.py`](../src/samsung_dplug/client.py) — `async_discover_duid`,
`async_get_state`, `async_set`, `async_get_sw_info`;
[`stream.py`](../src/samsung_dplug/stream.py) — `_handle`, `_merge`, `async_set`.*
