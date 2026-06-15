# Connection lifecycle & authentication

This page covers everything from the moment the TLS session is established to a
ready-to-use authenticated connection: the greeting, the one-time token
acquisition, per-connection authentication, and the device clock.

## Overview of a session

```
client                                   device
  │ ── TLS handshake (mutual, see transport.md) ──────────────► │
  │ ◄──────────────────────────────  DPLUG-1.x\r\n              │  greeting
  │ ◄────────────────  <Update Type="InvalidateAccount"/>       │  "please authenticate"
  │ ── <Request Type="AuthToken"><User Token="…"/></Request> ─► │
  │ ◄──  <Response Type="AuthToken" Status="Okay" StartFrom="…"/>│
  │ ── <Request Type="DeviceState" DUID="…"></Request> ───────► │
  │ ◄──  <Response Type="DeviceState" Status="Okay">…</Response> │
  │             … commands / pushes …                           │
```

## 1. Greeting

Immediately after the TLS handshake the device sends a line containing
**`DPLUG-1.x`** (e.g. `DPLUG-1.6`). Use it as a "this really is the protocol"
check; `async_probe()` does exactly this.

## 2. `InvalidateAccount`

The device then pushes:

```xml
<Update Type="InvalidateAccount"/>
```

It means *"no valid account on this connection — authenticate"*. It is also
re-sent by the streaming client's read loop as the trigger to (re)authenticate
after a reconnect. Treat its arrival as "now send `AuthToken`" (or, in AP mode,
"now send the provisioning command" — see [Provisioning](provisioning.md)).

## 3. Acquiring a token (`GetToken`) — one-time, LAN only

A token is a long-lived credential. You obtain it **once** per unit; it survives
reboots and is reused on every later connection.

```
←  <Request Type="GetToken" />
→  <Response Type="GetToken" Status="Ready"/>
   … user powers the indoor unit ON within ~30 s …
→  <Update Type="GetToken" Status="Completed" Token="xxxxxxxx-xxxx-…"/>
```

Critical details:

- **Powering the unit on is the proof-of-access step.** After `Status="Ready"`,
  the user must physically turn the AC **on** (from off) within ~30 s; the device
  then emits the `Token`. This prevents a network neighbour from silently
  pairing.
- **GetToken only works on the LAN.** In AP mode (`SMARTAIRCON`) the device
  ignores `GetToken` (and every other 2878 command) — see [Provisioning](provisioning.md).
- Save the token; never request another unless you reset the module.
- No DUID is needed for `GetToken`.

In the library: `await client.async_get_token()` (turn the unit off, call it,
turn it on within the window).

## 4. Authenticating (`AuthToken`) — every connection

Each new connection must authenticate after the greeting:

```
←  <Request Type="AuthToken"><User Token="xxxxxxxx-xxxx-…"/></Request>
→  <Response Type="AuthToken" Status="Okay" StartFrom="YYYY-MM-DD/HH:MM:SS"/>
```

- Success → `Status="Okay"`.
- A bad/rejected token → a `Status="Fail"` response mentioning `Auth`. This will
  **not** fix itself by reconnecting; surface it as a re-auth condition rather
  than retrying in a loop. (The streaming client sets `auth_failed` and stops.)

### `StartFrom` — the device clock

The `AuthToken` `Okay` response carries `StartFrom`, the **device's current time
in UTC** (`YYYY-MM-DD/HH:MM:SS`). This is the clock the module uses internally —
notably for [schedules](scheduling.md), which are stored in UTC. Parse it with
`parse_start_from()`; both clients expose it as `start_from`.

## Connection model

- **Short-lived client (`SamsungAcClient`).** Connect → authenticate → one
  exchange → close. Simple and robust; used for polling and one-off commands.
  Calls are serialised with a lock so a poll and a command never overlap.
- **Streaming client (`SamsungAcStream`).** Keeps **one** connection open for
  both receiving live pushes and sending commands (the module only likes one
  connection). It reconnects with backoff, re-authenticates on each
  `InvalidateAccount`, and runs a watchdog that periodically issues a
  `DeviceState` as a keepalive / fallback when no pushes arrive.

---
*Code: [`client.py`](../src/samsung_dplug/client.py) — `_connect`,
`_authenticate`, `async_get_token`, `parse_start_from`;
[`stream.py`](../src/samsung_dplug/stream.py) — `_read_loop`, `_handle`.*
