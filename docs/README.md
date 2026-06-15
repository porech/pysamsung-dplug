# Samsung DPLUG / AC14K protocol documentation

This directory documents the **DPLUG-1.x ("AC14K") protocol** spoken by older
Samsung air conditioners over TLS on **port 2878** — the WiFi modules of the
`SWL-Bxxx` family used by the `AR**HSFS*` generation (≈2013–2015), abandoned by
SmartThings.

It is the result of reverse-engineering the official *Smart Air Conditioner*
Android app (`com.samsung.rac`) together with live observation of real units. It
is the reference behind both [`pysamsung-dplug`](https://github.com/porech/pysamsung-dplug)
and the [`samsung_ac_dplug`](https://github.com/porech/samsung_ac_dplug) Home
Assistant integration.

> **Scope & status.** Everything here was verified either against firmware on
> real hardware or by decoding the official app. Where a detail comes only from
> the app (not yet confirmed live), it is marked *(from the app)*. The protocol
> has no official documentation; treat field lists as "complete to the best of
> our knowledge", not exhaustive.

## Contents

| Page | What it covers |
|------|----------------|
| [Transport & framing](transport.md) | TCP/2878, the legacy mutual-TLS handshake, the client certificate, XML framing, the DUID. |
| [Connection lifecycle & authentication](connection-and-auth.md) | Greeting, `InvalidateAccount`, `GetToken`, `AuthToken`, the device clock (`StartFrom`), connection model. |
| [State & control](state-and-control.md) | `DeviceList`, `DeviceState`, `DeviceControl`, live `Update`/`Status` pushes, the attribute (`AC_*`) reference. |
| [On-device scheduling](scheduling.md) | `Get`/`Set`/`DeleteSchedule`, the UTC clock, `DaySelection` bitmask, the midnight day-shift quirk. |
| [Other commands](commands.md) | Power-usage history & logging, nickname, region code, firmware versions. |
| [Capabilities — `AC_ADD2_OPTIONCODE`](capabilities.md) | The bitmask that tells you what a unit *actually* supports. |
| [WiFi provisioning (AP / WPS)](provisioning.md) | `APConnectionConfig` and the WPS onboarding path. |
| [Reverse-engineering notes](reverse-engineering.md) | How the protocol and the obfuscated app strings were decoded — so this can be extended. |

## Conventions used throughout

- All requests and responses are **single-line XML**, UTF-8, terminated by
  **`\r\n`**. There is **no `<?xml ?>` prologue**.
- In examples, `DUID`, tokens, SSIDs and IPs are **placeholders** — replace them
  with your own. The DUID is your WiFi module's MAC without separators
  (e.g. MAC `F8:04:2E:3F:89:A6` → DUID `F8042E3F89A6`).
- `→` means *device → client*, `←` means *client → device*.

## Relationship to the code

Each page links to where the behaviour lives in `pysamsung-dplug`. If you change
the protocol understanding, update both the relevant module and the page here.

## Mirroring to the GitHub Wiki (optional)

These pages are written to map 1:1 onto wiki pages. To publish them as a wiki,
copy each file to the `*.wiki.git` repo (the file name without `.md` becomes the
page title; `README.md` → `Home`). Keeping the source of truth here, in the main
repo, means it ships in the release, is reviewed via pull request, and never
drifts from the code it describes.
