"""Discord voice receive with real DAVE end-to-end encryption, offline.

scripts/dev/dave_loopback.py plays Discord's voice server to put two davey
sessions in one MLS group; the speaker's frames go through real DAVE and
transport encryption into voice_recv's own AudioReader.callback. Needs
`cryptography` (dev only) and libopus; skipped without them.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("cryptography")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dev"))

import dave_loopback  # noqa: E402
import discord.opus  # noqa: E402

from silenttalk import voice_recv_patch  # noqa: E402

try:
    discord.opus._load_default()
except Exception:  # noqa: BLE001 - no libopus on this machine
    pass
if not discord.opus.is_loaded():
    pytest.skip("libopus not available", allow_module_level=True)
voice_recv_patch.apply()

KEY = bytes(range(32))


def _speech() -> bytes:
    """One second of a voiced sound, 48 kHz stereo s16le."""
    t = np.arange(48_000) / 48_000
    wave = sum(np.sin(2 * np.pi * 150 * k * t) / k for k in range(1, 20)) * 3000
    return np.repeat(wave.astype("<i2"), 2).tobytes()


def test_every_frame_survives_dave_padding_and_silence() -> None:
    speaker, listener = dave_loopback.make_group()
    frames = dave_loopback.opus_frames(_speech())
    padded_before = voice_recv_patch.padded
    packets = dave_loopback.rtp_packets(frames, speaker, KEY, pad_every=3)

    assert dave_loopback.receive(packets, KEY, listener) == frames
    assert voice_recv_patch.padded - padded_before == len(range(0, len(frames), 3))
    stats = listener.get_decryption_stats(dave_loopback.SPEAKER_ID)
    assert stats.failures == 0


def test_undecrypted_frames_are_not_the_speech() -> None:
    speaker, _ = dave_loopback.make_group()
    frames = dave_loopback.opus_frames(_speech())
    packets = dave_loopback.rtp_packets(frames, speaker, KEY, pad_every=0)

    got = dave_loopback.receive(packets, KEY, None)  # what the old fork did

    speech = [f for f in frames if f != dave_loopback.SILENCE]
    assert not set(got) & set(speech)


def test_a_speaker_not_mapped_yet_is_dropped_and_counted() -> None:
    speaker, listener = dave_loopback.make_group()
    frames = dave_loopback.opus_frames(_speech())
    packets = dave_loopback.rtp_packets(frames, speaker, KEY, pad_every=0)
    before = voice_recv_patch.unknown_ssrc

    got = dave_loopback.receive(packets, KEY, listener, speaker_known=False)

    assert got == []  # voice_recv also skips silence from an unknown SSRC
    assert voice_recv_patch.unknown_ssrc - before == len(frames) - 5


def test_sustained_failures_report_the_last_transition_once() -> None:
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    reported: list[int] = []
    done = threading.Event()

    async def recover(transition_id: int) -> None:
        reported.append(transition_id)
        done.set()

    connection = SimpleNamespace(
        dave_session=object(),
        dave_pending_transitions={},
        _silenttalk_last_transition=5,
        _recover_from_invalid_commit=recover,
    )
    reader = SimpleNamespace(
        voice_client=SimpleNamespace(_connection=connection, loop=loop)
    )
    packet = SimpleNamespace(ssrc=7)
    try:
        for _ in range(voice_recv_patch.FAILURE_TOLERANCE):
            voice_recv_patch._track_failures(reader, packet, ok=False)
        assert not done.is_set()  # a few failures are normal when keys change
        voice_recv_patch._track_failures(reader, packet, ok=False)
        assert done.wait(2)
        for _ in range(3 * voice_recv_patch.FAILURE_TOLERANCE):  # cooling down
            voice_recv_patch._track_failures(reader, packet, ok=False)
        assert reported == [5]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(2)
        loop.close()


def test_no_recovery_while_a_transition_is_pending() -> None:
    connection = SimpleNamespace(
        dave_session=object(),
        dave_pending_transitions={6: 1},
        _silenttalk_last_transition=5,
        _recover_from_invalid_commit=None,
    )
    reader = SimpleNamespace(
        voice_client=SimpleNamespace(_connection=connection, loop=None)
    )
    for _ in range(2 * voice_recv_patch.FAILURE_TOLERANCE):
        voice_recv_patch._track_failures(reader, SimpleNamespace(ssrc=7), ok=False)
    assert not hasattr(connection, "_silenttalk_recovered_at")
