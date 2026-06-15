"""Async client for the Samsung 'DPLUG' air-conditioner protocol (TLS, port 2878).

Reverse-engineered from the AC14K / DPLUG-1.x firmware used by older Samsung
air conditioners with the SWL-Bxxx Wi-Fi modules. Mutual TLS using the public
Samsung client certificate (bundled ac14k_m.pem), with legacy ciphers enabled.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import re
import ssl
from importlib import resources
from xml.sax.saxutils import quoteattr

from .commands import (
    PowerUsageEntry,
    build_change_nickname,
    build_get_power_logging_mode,
    build_get_power_usage,
    build_get_region_code,
    build_reset_power_logging,
    build_set_power_logging_mode,
    build_set_region_code,
    parse_power_logging_mode,
    parse_power_usage,
    parse_region_code,
)
from .schedule import (
    Schedule,
    build_delete_schedule,
    build_get_schedule,
    build_set_schedule,
    parse_schedules,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 2878
_TERM = b"\r\n"
_ATTR_RE = re.compile(r'Attr ID="([^"]*)" Type="([^"]*)" Value="([^"]*)"')
_DUID_RE = re.compile(r'Device DUID="([^"]*)"')
_TOKEN_RE = re.compile(r'Token="([^"]*)"')
_STARTFROM_RE = re.compile(r'StartFrom="([^"]*)"')


def parse_start_from(line: str) -> "datetime.datetime | None":
    """Parse the device clock (UTC) from an AuthToken response StartFrom field."""
    m = _STARTFROM_RE.search(line)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d/%H:%M:%S").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None


class SamsungAcError(Exception):
    """Generic protocol error."""


class AuthError(SamsungAcError):
    """Authentication (token) rejected."""


def default_cert_path() -> str:
    """Path to the bundled Samsung client certificate."""
    return str(resources.files(__package__).joinpath("ac14k_m.pem"))


def build_ssl_context(cert_path: str | None = None) -> ssl.SSLContext:
    """Build the legacy mutual-TLS context. Blocking (file I/O) -> run in executor."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    ctx.set_ciphers("HIGH:!DH:!aNULL:@SECLEVEL=0")
    ctx.load_cert_chain(cert_path or default_cert_path())
    return ctx


async def async_probe(host: str, ssl_context: ssl.SSLContext, port: int = DEFAULT_PORT) -> bool:
    """Return True if `host` speaks the DPLUG protocol (used by discovery)."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context, server_hostname=host),
            timeout=8,
        )
    except (OSError, asyncio.TimeoutError, ssl.SSLError):
        return False
    try:
        line = await asyncio.wait_for(reader.readuntil(_TERM), 5)
        return "DPLUG" in line.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return False
    finally:
        writer.close()


class SamsungAcClient:
    """Short-lived-connection client: connect, auth, do one exchange, close.

    Serialised with a lock so polling and commands never overlap on the device
    (the module accepts essentially one connection at a time).
    """

    def __init__(self, host: str, token: str | None = None, ssl_context: ssl.SSLContext | None = None, duid: str | None = None, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._token = token
        self._ctx = ssl_context
        self._duid = duid
        self._lock = asyncio.Lock()
        self._start_from: datetime.datetime | None = None

    @property
    def duid(self) -> str | None:
        return self._duid

    @property
    def start_from(self) -> "datetime.datetime | None":
        """Device clock (UTC) as reported at the last authentication."""
        return self._start_from

    async def _readline(self, reader: asyncio.StreamReader, timeout: float = 5.0) -> str:
        data = await asyncio.wait_for(reader.readuntil(_TERM), timeout)
        return data.decode("utf-8", "replace").strip()

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                self._host, self._port, ssl=self._ctx, server_hostname=self._host
            ),
            timeout=10,
        )
        greeting = await self._readline(reader)
        if "DPLUG" not in greeting:
            writer.close()
            raise SamsungAcError(f"Unexpected greeting: {greeting!r}")
        return reader, writer

    async def _authenticate(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await self._readline(reader)
        if "InvalidateAccount" not in line:
            line = await self._readline(reader)
        writer.write(
            f'<Request Type="AuthToken"><User Token="{self._token}"/></Request>'.encode()
            + _TERM
        )
        await writer.drain()
        for _ in range(4):
            line = await self._readline(reader)
            if 'Type="AuthToken"' in line and 'Status="Okay"' in line:
                self._start_from = parse_start_from(line)
                return
            if 'Status="Fail"' in line and "Auth" in line:
                raise AuthError(f"Token rejected: {line}")
        raise AuthError("No AuthToken Okay received")

    @staticmethod
    def _parse_state(line: str) -> dict[str, str]:
        return {m[0]: m[2] for m in _ATTR_RE.findall(line)}

    async def _read_until(self, reader: asyncio.StreamReader, needle: str, timeout: float = 6.0) -> str:
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            line = await self._readline(reader, timeout=timeout)
            if needle in line:
                return line
        raise SamsungAcError(f"Timeout waiting for {needle}")

    async def async_discover_duid(self) -> str:
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(b'<Request Type="DeviceList"></Request>' + _TERM)
                await writer.drain()
                line = await self._read_until(reader, "DeviceList")
                m = _DUID_RE.search(line)
                if not m:
                    raise SamsungAcError(f"No DUID in DeviceList: {line}")
                self._duid = m.group(1)
                return self._duid
            finally:
                writer.close()

    async def _require_duid(self) -> str:
        if not self._duid:
            await self.async_discover_duid()
        assert self._duid is not None
        return self._duid

    async def async_get_state(self) -> dict[str, str]:
        if not self._duid:
            await self.async_discover_duid()
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(
                    f'<Request Type="DeviceState" DUID="{self._duid}"></Request>'.encode()
                    + _TERM
                )
                await writer.drain()
                line = await self._read_until(reader, 'Type="DeviceState"')
                if 'Status="Okay"' not in line:
                    raise SamsungAcError(f"DeviceState failed: {line}")
                return self._parse_state(line)
            finally:
                writer.close()

    async def async_set(self, attr: str, value: str) -> None:
        if not self._duid:
            await self.async_discover_duid()
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                cmd = (
                    f'<Request Type="DeviceControl"><Control CommandID="cmd" '
                    f'DUID="{self._duid}"><Attr ID="{attr}" Value="{value}" />'
                    f"</Control></Request>"
                )
                writer.write(cmd.encode() + _TERM)
                await writer.drain()
                line = await self._read_until(reader, 'Type="DeviceControl"')
                if 'Status="Okay"' not in line:
                    raise SamsungAcError(f"Control {attr}={value} failed: {line}")
            finally:
                writer.close()

    async def async_provision(self, ssid: str, key: str, auth_mode: str = "WPA2", encrypt_type: str = "AES") -> bool:
        """Send Wi-Fi credentials while the unit is in AP mode (host 192.168.1.254).

        Unauthenticated, sent right after InvalidateAccount. auth_mode in
        OPEN|WEP|WPA|WPA2, encrypt_type in TKIP|AES (ignored for OPEN/WEP).
        """
        async with self._lock:
            reader, writer = await self._connect()
            try:
                line = await self._readline(reader)
                if "InvalidateAccount" not in line:
                    line = await self._readline(reader)
                inner = f"<ConnectionConfig SSID={quoteattr(ssid)} AuthMode={quoteattr(auth_mode)}"
                if auth_mode == "WEP":
                    inner += f" Key1={quoteattr(key)}"
                elif auth_mode != "OPEN":
                    inner += f" EncryptType={quoteattr(encrypt_type)} Key1={quoteattr(key)}"
                inner += "/>"
                msg = f'<Request Type="APConnectionConfig">{inner}</Request>'
                writer.write(msg.encode() + _TERM)
                await writer.drain()
                resp = await self._read_until(reader, 'Type="APConnectionConfig"')
                if 'Status="Okay"' not in resp:
                    raise SamsungAcError(f"Provisioning failed: {resp}")
                return True
            finally:
                writer.close()

    async def async_get_sw_info(self) -> dict[str, str]:
        """Return firmware versions: {'sw':..., 'panel':..., 'outdoor':...}."""
        if not self._duid:
            await self.async_discover_duid()
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(
                    f'<Request Type="GetSWInfo" DUID="{self._duid}"></Request>'.encode() + _TERM
                )
                await writer.drain()
                line = await self._read_until(reader, 'Type="GetSWInfo"')
                out: dict[str, str] = {}
                for tag, key in (("SWInfo", "sw"), ("PannelInfo", "panel"), ("OutDoorInfo", "outdoor")):
                    m = re.search(tag + r' Version="([^"]*)"', line)
                    if m:
                        out[key] = m.group(1)
                return out
            finally:
                writer.close()

    async def async_get_schedules(self, tz: datetime.tzinfo = datetime.timezone.utc, now: datetime.datetime | None = None) -> list[Schedule]:
        """Return the schedules stored on the unit, in local (`tz`) terms."""
        if not self._duid:
            await self.async_discover_duid()
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(build_get_schedule(await self._require_duid()).encode() + _TERM)
                await writer.drain()
                line = await self._read_until(reader, 'Type="GetSchedule"')
                if 'Status="Okay"' not in line:
                    raise SamsungAcError(f"GetSchedule failed: {line}")
                return parse_schedules(line, tz, now)
            finally:
                writer.close()

    async def async_set_schedule(self, sched: Schedule, tz: datetime.tzinfo = datetime.timezone.utc, now: datetime.datetime | None = None) -> None:
        """Create (or, if `sched.schedule_id` is set, edit) an on-device schedule."""
        if not self._duid:
            await self.async_discover_duid()
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(build_set_schedule(sched, await self._require_duid(), tz, now).encode() + _TERM)
                await writer.drain()
                line = await self._read_until(reader, 'Type="SetSchedule"')
                if 'Status="Okay"' not in line:
                    raise SamsungAcError(f"SetSchedule failed: {line}")
            finally:
                writer.close()

    async def async_delete_schedule(self, schedule_id: str) -> None:
        """Delete the on-device schedule with the given id."""
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(build_delete_schedule(schedule_id).encode() + _TERM)
                await writer.drain()
                line = await self._read_until(reader, 'Type="DeleteSchedule"')
                if 'Status="Okay"' not in line:
                    raise SamsungAcError(f"DeleteSchedule failed: {line}")
            finally:
                writer.close()

    async def _exchange(self, payload: str, needle: str, *, need_duid: bool = False, check_okay: bool = True) -> str:
        """Connect, authenticate, send one request and return the matching response line."""
        if need_duid and not self._duid:
            await self.async_discover_duid()
        async with self._lock:
            reader, writer = await self._connect()
            try:
                await self._authenticate(reader, writer)
                writer.write(payload.encode() + _TERM)
                await writer.drain()
                line = await self._read_until(reader, needle)
                if check_okay and 'Status="Okay"' not in line:
                    raise SamsungAcError(f"{needle} failed: {line}")
                return line
            finally:
                writer.close()

    # -- power usage / logging (best-effort; may be unsupported on a given unit) --
    async def async_get_power_usage(self, date_from: datetime.datetime, date_to: datetime.datetime, unit: str = "Hour", tz: datetime.tzinfo = datetime.timezone.utc) -> list[PowerUsageEntry]:
        line = await self._exchange(build_get_power_usage(date_from, date_to, unit, tz), 'Type="GetPowerUsage"')
        return parse_power_usage(line, tz)

    async def async_get_power_logging_mode(self) -> bool | None:
        line = await self._exchange(build_get_power_logging_mode(), 'Type="GetPowerLoggingMode"')
        return parse_power_logging_mode(line)

    async def async_set_power_logging(self, enable: bool) -> None:
        await self._exchange(build_set_power_logging_mode(enable), 'Type="SetPowerLoggingMode"')

    async def async_reset_power_logging(self) -> None:
        await self._exchange(build_reset_power_logging(), 'Type="ResetPowerLogging"')

    # -- nickname / region (best-effort) --
    async def async_set_nickname(self, nickname: str) -> None:
        await self._exchange(build_change_nickname(await self._require_duid(), nickname), 'Type="ChangeNickname"')

    async def async_get_region_code(self) -> str | None:
        line = await self._exchange(build_get_region_code(), 'Type="GetRegionCode"')
        return parse_region_code(line)

    async def async_set_region_code(self, code: str) -> None:
        await self._exchange(build_set_region_code(await self._require_duid(), code), 'Type="SetRegionCode"')

    async def async_get_token(self, power_on_timeout: float = 40.0) -> str:
        """One-shot token acquisition. User must power the unit ON during the window."""
        async with self._lock:
            reader, writer = await self._connect()
            try:
                line = await self._readline(reader)
                if "InvalidateAccount" not in line:
                    line = await self._readline(reader)
                writer.write(b'<Request Type="GetToken" />' + _TERM)
                await writer.drain()
                await self._read_until(reader, 'Type="GetToken"')  # Ready
                token_line = await self._read_until(reader, "Token=", timeout=power_on_timeout)
                m = _TOKEN_RE.search(token_line)
                if not m:
                    raise SamsungAcError(f"No token in: {token_line}")
                return m.group(1)
            finally:
                writer.close()
