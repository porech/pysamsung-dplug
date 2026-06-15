"""Tests for SamsungAcStream message routing (_handle/_merge/waiters), no sockets."""
import asyncio

import pytest

from samsung_dplug import SamsungAcError
from samsung_dplug.stream import SamsungAcStream

TERM_AUTH = '<Request Type="AuthToken">'


def _stream(duid="F8042E3F89A6"):
    s = SamsungAcStream("host", "tok", ssl_context=None, duid=duid)
    sent: list[str] = []

    async def fake_send(payload):  # bypass the real socket
        sent.append(payload)

    s._send = fake_send
    return s, sent


def test_invalidate_account_triggers_auth():
    async def run():
        s, sent = _stream()
        await s._handle('<Update Type="InvalidateAccount"/>')
        assert any('Type="AuthToken"' in p and "tok" in p for p in sent)

    asyncio.run(run())


def test_auth_ok_requests_state_and_captures_clock():
    async def run():
        s, sent = _stream()
        await s._handle('<Response Type="AuthToken" Status="Okay" StartFrom="2026-06-17/09:30:00"/>')
        assert any('Type="DeviceState"' in p for p in sent)
        assert s.start_from is not None and s.start_from.year == 2026

    asyncio.run(run())


def test_auth_fail_sets_flag_and_raises():
    async def run():
        s, _ = _stream()
        with pytest.raises(SamsungAcError):
            await s._handle('<Response Type="AuthToken" Status="Fail" ErrorCode="105"/>')
        assert s.auth_failed is True

    asyncio.run(run())


def test_device_state_merges_and_marks_connected_and_notifies():
    async def run():
        s, _ = _stream()
        seen = []
        s.set_on_update(lambda state: seen.append(state))
        line = (
            '<Response Type="DeviceState" Status="Okay">'
            '<Attr ID="AC_FUN_POWER" Type="RW" Value="On"/>'
            '<Attr ID="AC_FUN_TEMPSET" Type="RW" Value="24"/></Response>'
        )
        await s._handle(line)
        assert s.connected is True
        assert s.state["AC_FUN_POWER"] == "On"
        assert seen and seen[-1]["AC_FUN_TEMPSET"] == "24"

    asyncio.run(run())


def test_status_push_resolves_confirm_waiter():
    async def run():
        s, _ = _stream()
        # seed connected state
        await s._handle('<Response Type="DeviceState" Status="Okay"><Attr ID="AC_FUN_POWER" Value="Off"/></Response>')
        fut = s._wait_confirm("AC_FUN_POWER", "On", timeout=1.0)
        await s._handle('<Update Type="Status"><Attr ID="AC_FUN_POWER" Value="On"/></Update>')
        assert await fut is True

    asyncio.run(run())


def test_response_waiter_resolves_on_matching_line():
    async def run():
        s, _ = _stream()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        s._resp_waiters.append(('Type="GetSchedule"', fut))
        line = '<Response Type="GetSchedule" Status="Okay" DUID="D"/>'
        await s._handle(line)
        assert fut.result() == line

    asyncio.run(run())
