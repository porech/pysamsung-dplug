# Reverse-engineering notes

How the protocol described here was recovered, so others can verify it and
extend it.

## Sources

- The official **Smart Air Conditioner** Android app, `com.samsung.rac` (a 2020
  APK), which speaks this protocol to the same modules.
- **Live observation** of real units on the LAN (greeting, token flow, state
  dumps, schedule round-trips, provisioning responses).
- Prior community work that established the transport and the bundled
  certificate (see [References](#references)).

## Toolchain

| Tool | Used for |
|------|----------|
| [jadx](https://github.com/skylot/jadx) | Decompiling the APK to readable Java. |
| [dex2jar](https://github.com/pxb1988/dex2jar) | Converting the app's `.dex` to a `.jar` so its own code can be executed. |
| a JDK | Running small reflection harnesses against that jar. |
| `openssl s_client` / Python `ssl` | Probing the TLS handshake and the line protocol. |

## The obfuscated-strings problem

The app does **not** carry the XML tag/attribute names as plain strings. They are
**encrypted** (an XOR against a large in-app table) and decrypted at runtime.
Reading the decompiled source alone therefore shows opaque calls, not
`Type="SetSchedule"`.

The practical way through was to **let the app decrypt its own strings**:

1. `dex2jar` the APK into a jar.
2. Load that jar and, via **Java reflection**, call the app's own string-decoder
   with the obfuscated indices found in the decompiled builders.
3. Read back the cleartext tag/attribute names.

This is how the wire vocabulary for schedules, power usage, nickname, region
code and provisioning was recovered (e.g. the schedule classes in
`com.samsung.rac.dataset`, `APConnectionConfigRequest.toXml()`,
`OptionCodeHelper`). The XML builder helper class itself uses terse methods
(`a(tag)` = open, `a(k,v)` = attribute, `b(tag)` = close), so the structure had
to be read off the call sequence and confirmed against live responses.

## Verifying against hardware

Every wire shape here was confirmed against a real unit where possible:
greeting + `InvalidateAccount`, the `GetToken` power-on handshake, `AuthToken`
with `StartFrom`, `DeviceState`/`DeviceControl` round-trips, a `SetSchedule` that
the device accepted and later fired, and an `APConnectionConfig` that moved a
module onto a new network. Details that come only from the app and were not
exercised live are flagged as *(from the app)* on their pages.

## Notes

- The native `libbrolib-ajni.so` is Samsung's anti-tamper (SXA) layer only; it
  contains no protocol logic, so it did not need to be analysed for this.
- If you extend the protocol coverage, please confirm against a real unit and
  note whether each new detail is live-verified or app-only.

## References

Community projects that informed the transport, the `ac14k_m.pem` certificate
and the token flow:

- `SebuZet/samsungrac` — Home Assistant component for the 2878 protocol.
- `SebastianOsinski/HomebridgePluginSamsungAirConditioner` — the
  `GetToken`/`AuthToken` flow.
- `cicciovo/homebridge-samsung-airconditioner` — the `ac14k_m.pem` certificate.
