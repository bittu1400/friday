"""Resilience and fault-tolerance tests (NFR-9, NFR-10, architecture.md §8).

Verifies that Friday recovers cleanly from transient subsystem failures:
  - LLM server death and recovery (NFR-9)
  - Audio device loss and stream recreation (NFR-10)
  - Startup cold-start retry loop (wait_for_llm)
"""

import asyncio
import json
from unittest.mock import MagicMock, patch
import pytest

from friday.audio.capture import Recorder
from friday.llm.client import LlamaClient, LlamaUnreachable
from friday.turn import run_turn
from friday.voice_main import wait_for_llm


def test_nfr9_survives_llm_crash_and_recovers():
    """NFR-9: Survives kill of llama-server and recovers on next turn."""
    client = LlamaClient(base_url="http://127.0.0.1:8080")

    # Turn 1: LLM server crashes mid-request (connection refused / dropped)
    with patch.object(LlamaClient, "complete", side_effect=LlamaUnreachable("Connection refused")):
        res1 = asyncio.run(
            run_turn(
                "open terminal",
                client,
                request_id="req_crash_1",
                dry_run=True,
            )
        )
        assert res1.plan_name == "none"
        assert res1.spoken == "My brain's offline."
        assert not res1.dispatched

    # Turn 2: LLM server is back online -> next turn works cleanly
    with patch.object(
        LlamaClient,
        "complete",
        return_value='{"action": {"name": "open_app", "params": {"app": "terminal"}}}',
    ):
        res2 = asyncio.run(
            run_turn(
                "open terminal",
                client,
                request_id="req_recover_2",
                dry_run=True,
            )
        )
        assert res2.plan_name == "open_app"
        assert res2.dispatched
        assert "foot" in res2.spoken.lower() or "terminal" in res2.spoken.lower()


def test_nfr10_audio_device_recovery_on_suspend_resume():
    """NFR-10: Survives audio device disconnect/suspend by recreating stream."""
    r = Recorder(gate=lambda: True)

    mock_stream = MagicMock()
    mock_stream.active = True

    with patch("sounddevice.InputStream", return_value=mock_stream):
        # Initial open
        opened = r.open()
        assert opened
        assert r.is_active

        # Simulate audio device drop during suspend/resume
        mock_stream.active = False
        assert not r.is_active

        # ensure_open should automatically close the stale stream and open a new one
        mock_new_stream = MagicMock()
        mock_new_stream.active = True
        with patch("sounddevice.InputStream", return_value=mock_new_stream):
            recovered = r.ensure_open()
            assert recovered
            assert r.is_active


def test_wait_for_llm_retries_and_succeeds():
    """Startup ping tolerates server loading weights then succeeding."""
    calls = 0

    def mock_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("Connection refused")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        ok = wait_for_llm("http://127.0.0.1:8080", timeout_s=5.0, poll_interval_s=0.01)
        assert ok is True
        assert calls == 3


def test_wait_for_llm_times_out_gracefully():
    """Startup ping handles unreachable server without crashing."""
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        ok = wait_for_llm("http://127.0.0.1:8080", timeout_s=0.05, poll_interval_s=0.01)
        assert ok is False
