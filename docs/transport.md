# Transport & framing

## TCP

- The module listens on **TCP port `2878`** only. There is no UDP control
  channel. (Discovery, if any, is via SSDP/mDNS on the LAN, but the units in our
  testing did not announce reliably — probe `2878` directly instead.)
- One connection at a time. The module effectively accepts a **single client
  connection**; a second connection while one is open is unreliable. Serialise
  access (the library uses a per-client lock, and the streaming client shares one
  socket for both reads and writes for this reason).

## TLS (legacy — this is the tricky part)

The firmware is from ~2013–2015 and the TLS stack reflects it. A modern client
**must downgrade** to talk to it:

| Setting | Value | Why |
|---------|-------|-----|
| Protocol | **TLS 1.0** minimum | The module does not negotiate TLS 1.2+. |
| Cipher | **`AES256-SHA`** (from `HIGH:!DH:!aNULL`) | Only weak ciphers are offered. |
| OpenSSL security level | **`@SECLEVEL=0`** | Modern OpenSSL refuses TLS 1.0 / SHA1 ciphers otherwise. |
| Mutual TLS | **client certificate required** | The server requests a client cert during the handshake; without it you get `SSLV3_ALERT_HANDSHAKE_FAILURE`. |
| Server verification | **disabled** | The server presents a self-signed Samsung certificate; there is no CA to validate it against. |

### The client certificate

The handshake requires a **public Samsung client certificate**, `ac14k_m.pem`:
an RSA private key plus the Samsung certificate chain (subject `AC14K_M`). It is
not a secret — it is baked into the app and shipped by every community client.
This library bundles it (`samsung_dplug/ac14k_m.pem`); see
[`build_ssl_context()`](../src/samsung_dplug/client.py).

```python
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
ctx.minimum_version = ssl.TLSVersion.TLSv1
ctx.set_ciphers("HIGH:!DH:!aNULL:@SECLEVEL=0")
ctx.load_cert_chain("ac14k_m.pem")        # blocking file I/O — run in an executor
```

> `load_cert_chain` does blocking file I/O. Inside an async framework (e.g. Home
> Assistant) build the context in an executor, or the event loop stalls.

## Framing

Once the TLS session is up, the protocol is line-oriented XML:

- Every message is **one line of UTF-8 XML** terminated by **`\r\n`**.
- There is **no `<?xml ?>` prologue** — sending one is unnecessary and the
  provisioning path specifically must omit it.
- Read by reading until `\r\n`; write by appending `\r\n`.
- Responses are matched by substring (`Type="..."`, `Status="..."`) rather than
  by full XML parsing on the hot path, because the device interleaves
  unsolicited messages (see [State & control](state-and-control.md)).

## The DUID

The **DUID** identifies the indoor unit and equals the **WiFi module's MAC
address without separators**, uppercase:

```
MAC F8:04:2E:3F:89:A6  →  DUID F8042E3F89A6
```

- Most stateful requests (`DeviceState`, `DeviceControl`, `GetSchedule`,
  `SetSchedule`, `GetSWInfo`, …) **require** the DUID. Omitting it returns
  `Status="Fail" ... ErrorCode="103"`.
- `DeleteSchedule`, `GetToken`, `AuthToken` and the provisioning command do
  **not** carry a DUID.
- If you don't know the DUID, discover it with `DeviceList` after authenticating
  (see [Connection lifecycle](connection-and-auth.md)).

One physical outdoor unit driving several indoor splits exposes **one DUID per
indoor unit / WiFi module**, each with its own token.

---
*Code: [`client.py`](../src/samsung_dplug/client.py) — `build_ssl_context`,
`default_cert_path`, `async_probe`.*
