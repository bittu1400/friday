"""PTT socket: command parsing (closed set, fail closed) and a real
serve<->send round trip over a unix socket."""

import asyncio
import stat

import pytest

from friday.audio import ptt


def test_parse_valid_commands():
    assert ptt.parse_command(b"press\n") == "press"
    assert ptt.parse_command(b"  RELEASE  ") == "release"  # trimmed, lowered
    assert ptt.parse_command(b"toggle\n") == "toggle"
    assert ptt.parse_command(b"cancel") == "cancel"


def test_parse_rejects_unknown_fail_closed():
    for bad in (b"", b"open_app firefox\n", b"press; rm -rf\n", b"\x00\x01"):
        assert ptt.parse_command(bad) is None


def test_send_unknown_command_raises(tmp_path):
    with pytest.raises(ValueError):
        ptt.send(tmp_path / "x.sock", "explode")


def test_send_to_no_daemon_is_quiet_false(tmp_path):
    assert ptt.send(tmp_path / "absent.sock", "press") is False


def test_round_trip_valid_and_invalid(tmp_path):
    sock = tmp_path / "ptt.sock"
    seen: list[str] = []

    async def scenario() -> None:
        async def on_event(cmd: str) -> None:
            seen.append(cmd)

        server = await ptt.serve(sock, on_event)
        try:
            mode = stat.S_IMODE(sock.stat().st_mode)
            assert mode == 0o600, oct(mode)  # socket file user-only

            for cmd in ("press", "release", "cancel"):
                assert await asyncio.to_thread(ptt.send, sock, cmd) is True
            # invalid commands can't go through send(); push a raw bad line
            _, w = await asyncio.open_unix_connection(str(sock))
            w.write(b"open_app firefox\n")
            await w.drain()
            w.close()
            await asyncio.sleep(0.05)  # let handlers run
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())
    assert seen == ["press", "release", "cancel"]  # bad line dispatched nothing
