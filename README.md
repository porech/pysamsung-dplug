# pysamsung-dplug

Async Python client for **old Samsung air conditioners** that speak the legacy
**DPLUG / AC14K** protocol over TLS on **port 2878** (Wi-Fi modules such as
`SWL-B70F`, used by the AR\*\*HSFS generation, ~2013–2015).

These units were dropped by SmartThings. This library lets you control them
locally again — no cloud. It is the protocol layer used by the
[`samsung_ac_dplug`](https://github.com/porech/samsung_ac_dplug) Home Assistant
integration, but works standalone.

## Features

- Mutual-TLS handshake with the bundled Samsung client certificate (legacy
  TLS 1.0 / weak ciphers handled for you).
- Token acquisition (`GetToken`), authentication (`AuthToken`).
- Read full device state (`DeviceState`) and send commands (`DeviceControl`).
- Auto-discover the device id (`DeviceList`) and a passive `async_probe()`.

## Install

```bash
pip install pysamsung-dplug
```

## Usage

```python
import asyncio
from samsung_dplug import SamsungAcClient, build_ssl_context

async def main():
    ctx = build_ssl_context()                      # uses the bundled certificate
    client = SamsungAcClient("192.168.1.53", token="xxxxxxxx-....", ssl_context=ctx)
    state = await client.async_get_state()
    print("Power:", state["AC_FUN_POWER"], "Room:", state["AC_FUN_TEMPNOW"])
    await client.async_set("AC_FUN_POWER", "On")

asyncio.run(main())
```

### Getting a token

The unit only issues a token at **power-on** (a physical proof-of-access step):

```python
client = SamsungAcClient("192.168.1.53", ssl_context=ctx)
# turn the unit OFF, call this, then turn it ON within ~30 s:
token = await client.async_get_token()
```

> `build_ssl_context()` does blocking file I/O; inside async frameworks run it in
> an executor (e.g. Home Assistant: `await hass.async_add_executor_job(build_ssl_context)`).

## Protocol notes

Reverse-engineered from the official *Smart Air Conditioner* app and live
devices. The unit greets with `DPLUG-1.x`, requires mutual TLS, and uses an
XML request/response protocol. The DUID equals the Wi-Fi module MAC without
separators. See the Home Assistant integration repo for the full write-up,
including the undocumented `APConnectionConfig` Wi-Fi provisioning command.

## License

MIT
