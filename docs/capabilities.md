# Capabilities — `AC_ADD2_OPTIONCODE`

A unit reports a large, partly model-specific attribute set, and it **reports
attributes for features it does not actually have**. So you cannot decide what a
unit supports by looking at which `AC_*` attributes are present.

The authoritative source is a single integer attribute, **`AC_ADD2_OPTIONCODE`**,
a **bitmask of capability flags**. This is exactly what the official app uses
(class `OptionCodeHelper`); a feature is present when `(code & mask) == mask`.

## Flags

| Bit (mask) | Name | Meaning |
|-----------:|------|---------|
| 1 | `EGYPT` | Egypt market variant. |
| 2 | `SPI` | SPi / Virus Doctor purification. |
| 4 | `FAHRENHEIT` | Temperatures (setpoint & room) are in °F. |
| 8 | `TURBO_HEATMODE` | Turbo / SoftCool preset available. |
| 16 | `ECORUN_HEATMODE` | Eco-run in heating. |
| 32 | `LOW_SOUND` | Quiet preset. |
| 64 | `COOL_ONLY` | **Cooling-only unit** → *heating available == NOT this bit*. |
| 128 | `COLOR_OF_WIND` | "Color of wind". |
| 256 | `COLD_AREA` | Cold-area model. |
| 512 | `ENERGY_SIMULATOR` | Energy simulator. |
| 1024 | `LR_LOUVER` | **Left/right (horizontal) swing.** |
| 2048 | `HUMID_SENSOR` | Humidity sensor. |
| 4096 | `ECORUN_COOLMODE` | Eco-run in cooling. |
| 8192 | `DLIGHT_COOL` | D-light cool. |
| 16384 | `POWER_CONSUMPTION_TYPE` | Power-usage logging ([`GetPowerUsage`](commands.md)). |
| 32768 | `INV_TYPE` | Inverter. |

Two non-obvious ones:

- **`COOL_ONLY`** is inverted: heating is available when the bit is **clear**
  (`heater == not COOL_ONLY`).
- **`SPI`** off means you should **hide** the `AC_ADD_SPI` attribute even though
  the device still reports it.

## Worked example

`OPTIONCODE = 32936` decomposes as `32768 + 128 + 32 + 8` =
`INV_TYPE + COLOR_OF_WIND + LOW_SOUND + TURBO_HEATMODE`. So that unit:

- ✅ inverter, Quiet preset, Turbo/SoftCool, color-of-wind
- ✅ heating (the `COOL_ONLY` bit is clear)
- ❌ horizontal swing (`LR_LOUVER` clear), SPi, power-usage logging, humidity
  sensor, Fahrenheit

## Library mapping

```python
from samsung_dplug import OptionCode

state = await client.async_get_state()
opt = OptionCode.from_state(state)        # None if the attr is absent/non-numeric
if opt and opt.heater:
    ...                                   # expose Heat mode
opt.as_dict()                             # {'inverter': True, 'quiet': True, ...}
```

Property names mirror the app's intent (`heater`, `quiet`, `turbo_softcool`,
`lr_swing`, `usage`, `inverter`, …). See [`options.py`](../src/samsung_dplug/options.py).

---
*Code: [`options.py`](../src/samsung_dplug/options.py).*
