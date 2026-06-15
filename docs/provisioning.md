# WiFi provisioning (AP / WPS)

Getting a factory-reset module onto your home WiFi is the trickiest part,
because **the 2878 protocol is inert in AP mode** for almost everything. There
are two paths: **WPS** (works with the physical remote, no app) and
**`APConnectionConfig`** (the app's path, reverse-engineered from it).

## AP mode

When unprovisioned the module raises its own access point:

- SSID **`SMARTAIRCON`**, default password `1111122222`, device IP
  **`192.168.1.254`**.
- On the remote of these models (no dedicated WiFi/WPS buttons), **hold `Timer`
  for ~4 s** to toggle the WiFi/AP function.

In AP mode the module greets with `DPLUG-1.x` and sends `InvalidateAccount`, then
**ignores GetToken, DeviceState, DeviceControl, etc.** Do not try to provision
over 2878 the "normal" way — it won't answer. Use one of the two paths below.

## Path A — WPS (recommended, no app)

1. Make sure the AC is **not** in AP mode.
2. On the remote, **hold `Settings` for ~4 s** — this starts **WPS (PBC)**. It is
   a *hidden* function: the only feedback is a brief blink on the display.
3. Within ~2 minutes, **press the WPS button on your router**.
4. On success the module's **WiFi LED goes solid**, and state reflects
   `AC_ADD_APMODE_END="WPS"`.

After it joins your LAN, continue with [token acquisition](connection-and-auth.md#3-acquiring-a-token-gettoken--one-time-lan-only).

## Path B — `APConnectionConfig` (the app's method)

While the client is connected to the `SMARTAIRCON` AP, the app pushes the WiFi
credentials, **unauthenticated**, right after `InvalidateAccount`:

```xml
<Request Type="APConnectionConfig"><ConnectionConfig SSID="<your-ssid>" AuthMode="WPA2" EncryptType="AES" Key1="<your-password>"/></Request>
```

```
→  <Response Type="APConnectionConfig" Status="Okay"/>
```

…after which the module leaves the AP and joins the named network.

Field rules:

| `AuthMode` | `EncryptType` | `Key1` |
|------------|---------------|--------|
| `OPEN` | *(omitted)* | *(omitted)* |
| `WEP` | *(omitted)* | the key |
| `WPA` | `TKIP` | the key |
| `WPA2` | `AES` | the key |

(`EncryptType` is `TKIP` or `AES`; the app maps WPA2→AES, WPA→TKIP.)

**Framing (confirmed live):** no `<?xml ?>` prologue, `\r\n` terminator, **no
authentication** (there is no token yet). Send it as soon as you see
`InvalidateAccount`.

```python
# host is the AP gateway, 192.168.1.254
client = SamsungAcClient("192.168.1.254", ssl_context=ctx)
await client.async_provision("<your-ssid>", "<your-password>", "WPA2", "AES")
```

## Related state attributes

Seen in `DeviceState` around provisioning: `AC_ADD_WIFIMODE`,
`AC_ADD_APMODE_END`, `AC_ADD_STARTWPS`, `AC_ADD_WPS_END`.

> The native `libbrolib-ajni.so` in the app is only Samsung's anti-tamper (SXA)
> layer — it contains **no** protocol logic.

---
*Code: [`client.py`](../src/samsung_dplug/client.py) — `async_provision`.*
