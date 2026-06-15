"""Persistent-connection client with live push updates and auto-reconnect.

A single TLS connection is used for BOTH listening (the device pushes
``<Update Type="Status">`` messages when state changes) AND sending commands —
the module accepts essentially one connection at a time, so sharing it is
required. The read loop reconnects automatically; a watchdog periodically polls
(DeviceState) as a keepalive and as a fallback when no pushes arrive.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable

from .client import SamsungAcError, _DUID_RE, _TERM, parse_start_from

_LOGGER = logging.getLogger(__name__)

# Matches attrs both in DeviceState (ID/Type/Value) and Status pushes (ID/Value).
_ATTR_ANY = re.compile(r'Attr ID="([^"]*)"[^>]*?Value="([^"]*)"')


class SamsungAcStream:
    def __init__(
        self,
        host: str,
        token: str,
        ssl_context,
        duid: str | None = None,
        port: int = 2878,
        on_update: Callable[[dict], None] | None = None,
        fallback_interval: float = 300.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._token = token
        self._ctx = ssl_context
        self._duid = duid
        self._on_update = on_update
        self._fallback = fallback_interval
        self._log = logger or _LOGGER
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._state: dict = {}
        self._ready = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._closing = False
        self._reader_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._last_rx = 0.0
        self._waiters: list = []  # (predicate(state)->bool, Future)
        self.auth_failed = False
        self.start_from = None  # device clock (UTC) from the AuthToken response

    # -- public API ----------------------------------------------------
    def set_on_update(self, callback: Callable[[dict], None] | None) -> None:
        """Register a callback invoked (in the event loop) on each state change."""
        self._on_update = callback

    @property
    def state(self) -> dict:
        return dict(self._state)

    @property
    def duid(self) -> str | None:
        return self._duid

    @property
    def connected(self) -> bool:
        return self._ready.is_set()

    async def start(self) -> None:
        self._closing = False
        loop = asyncio.get_running_loop()
        self._reader_task = loop.create_task(self._read_loop())
        self._watchdog_task = loop.create_task(self._watchdog())
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=25)
        except asyncio.TimeoutError:
            self._log.warning("Samsung AC stream: initial connection timed out (will keep retrying)")

    async def stop(self) -> None:
        self._closing = True
        for t in (self._reader_task, self._watchdog_task):
            if t:
                t.cancel()
        await self._close_socket()

    async def async_set(self, attr: str, value: str, confirm: bool = True, confirm_timeout: float = 8.0) -> bool:
        """Send a command and (by default) wait until the device confirms the new
        value via a push, so callers can show a pending->applied state with no flicker.
        Returns True if confirmed within the timeout."""
        cmd = (
            f'<Request Type="DeviceControl"><Control CommandID="cmd" '
            f'DUID="{self._duid}"><Attr ID="{attr}" Value="{value}" /></Control></Request>'
        )
        try:
            await self._ensure_ready()
            await self._send(cmd)
        except (OSError, SamsungAcError, asyncio.TimeoutError) as err:
            self._log.debug("command send failed (%s); reconnecting and retrying", err)
            await self._force_reconnect()
            await self._ensure_ready()
            await self._send(cmd)
        if confirm:
            return await self._wait_confirm(attr, value, confirm_timeout)
        return True

    async def _wait_confirm(self, attr: str, value: str, timeout: float) -> bool:
        target = str(value)
        if str(self._state.get(attr)) == target:
            return True
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        pred = lambda st, a=attr, t=target: str(st.get(a)) == t  # noqa: E731
        self._waiters.append((pred, fut))
        try:
            await asyncio.wait_for(fut, timeout)
            return True
        except asyncio.TimeoutError:
            return str(self._state.get(attr)) == target
        finally:
            self._waiters = [(p, f) for (p, f) in self._waiters if f is not fut]

    def _resolve_waiters(self) -> None:
        if not self._waiters:
            return
        still = []
        for pred, fut in self._waiters:
            if fut.done():
                continue
            if pred(self._state):
                fut.set_result(True)
            else:
                still.append((pred, fut))
        self._waiters = still

    async def async_refresh(self) -> None:
        """Request a full DeviceState now (used as the fallback poll)."""
        if self._duid:
            await self._ensure_ready()
            await self._send(f'<Request Type="DeviceState" DUID="{self._duid}"></Request>')

    # -- internals -----------------------------------------------------
    async def _ensure_ready(self, timeout: float = 20.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    async def _send(self, payload: str) -> None:
        if self._writer is None:
            raise SamsungAcError("not connected")
        async with self._write_lock:
            self._writer.write(payload.encode() + _TERM)
            await self._writer.drain()

    async def _close_socket(self) -> None:
        self._ready.clear()
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001
                pass
        self._reader = self._writer = None

    async def _force_reconnect(self) -> None:
        await self._close_socket()  # read loop will notice and reconnect
        try:
            await self._ensure_ready(timeout=20)
        except asyncio.TimeoutError:
            pass

    async def _open(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port, ssl=self._ctx, server_hostname=self._host),
            timeout=10,
        )
        line = (await asyncio.wait_for(reader.readuntil(_TERM), 5)).decode("utf-8", "replace").strip()
        if "DPLUG" not in line:
            writer.close()
            raise SamsungAcError(f"unexpected greeting: {line!r}")
        self._reader, self._writer = reader, writer

    async def _read_loop(self) -> None:
        backoff = 2
        loop = asyncio.get_running_loop()
        while not self._closing:
            try:
                await self._open()
                while not self._closing:
                    data = await self._reader.readuntil(_TERM)
                    self._last_rx = loop.time()
                    await self._handle(data.decode("utf-8", "replace").strip())
                    backoff = 2
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                if self._closing or self.auth_failed:
                    # auth failure won't fix itself by reconnecting -> stop and
                    # let the integration trigger a reauth flow.
                    await self._close_socket()
                    break
                self._log.debug("Samsung AC stream disconnected: %s (retry in %ss)", err, backoff)
                await self._close_socket()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _handle(self, line: str) -> None:
        if not line:
            return
        if "InvalidateAccount" in line:
            await self._send(f'<Request Type="AuthToken"><User Token="{self._token}"/></Request>')
        elif 'Type="AuthToken"' in line and 'Status="Okay"' in line:
            self.start_from = parse_start_from(line)
            if self._duid:
                await self._send(f'<Request Type="DeviceState" DUID="{self._duid}"></Request>')
            else:
                await self._send('<Request Type="DeviceList"></Request>')
        elif 'Status="Fail"' in line and "Auth" in line:
            self.auth_failed = True
            raise SamsungAcError(f"auth failed: {line}")
        elif 'Type="DeviceList"' in line:
            m = _DUID_RE.search(line)
            if m:
                self._duid = m.group(1)
                await self._send(f'<Request Type="DeviceState" DUID="{self._duid}"></Request>')
        elif 'Type="DeviceState"' in line and 'Status="Okay"' in line:
            self._merge(line, full=True)
        elif "InvalidateAccount" not in line and ("Update" in line or "DeviceControl" in line):
            # Status pushes and control acks carry Attr ID/Value pairs.
            self._merge(line, full=False)

    def _merge(self, line: str, full: bool) -> None:
        attrs = {k: v for k, v in _ATTR_ANY.findall(line)}
        if not attrs and not full:
            return
        self._state.update(attrs)
        self._resolve_waiters()
        if full and not self._ready.is_set():
            self._ready.set()
        if self._on_update:
            try:
                self._on_update(self.state)
            except Exception:  # noqa: BLE001
                self._log.exception("on_update callback failed")

    async def _watchdog(self) -> None:
        try:
            while not self._closing:
                await asyncio.sleep(self._fallback)
                if self._closing:
                    break
                try:
                    await self.async_refresh()
                except Exception as err:  # noqa: BLE001
                    self._log.debug("watchdog refresh failed: %s", err)
                    await self._force_reconnect()
        except asyncio.CancelledError:
            raise
