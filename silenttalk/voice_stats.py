from __future__ import annotations

import logging

import discord

from silenttalk import voice_recv_patch

_LOG = logging.getLogger(__name__)
FRAME_BYTES = 3840


def dave_receive_ready(voice: discord.VoiceClient) -> bool:
    """voice_recv decrypts DAVE frames with discord.py's session and drops the
    ones it can't; frames arriving while there is no session were not
    decrypted at all."""
    connection = getattr(voice, "_connection", None)
    if int(getattr(connection, "dave_protocol_version", 0) or 0) == 0:
        return True
    return getattr(connection, "dave_session", None) is not None


class ReceiveStats:
    """How voice arrives, in numbers only (no audio, no names): frames per
    second per speaker (50 is every frame), frames of an unexpected size,
    frames dropped for lack of a DAVE session, Opus decode errors, and the
    DAVE session's own decrypt counters per speaker."""

    PERIOD = 30.0

    def __init__(self, started: float) -> None:
        self.started = started
        self.frames: dict[int, int] = {}
        self.odd = 0
        self.dropped = 0
        self.patch_before = _patch_counters()

    def frame(self, user_id: int, size: int) -> None:
        self.frames[user_id] = self.frames.get(user_id, 0) + 1
        if size != FRAME_BYTES:
            self.odd += 1

    def log(
        self, voice: discord.VoiceClient | None, now: float, members: list[int]
    ) -> None:
        seconds = max(now - self.started, 1e-3)
        connection = getattr(voice, "_connection", None)
        version = int(getattr(connection, "dave_protocol_version", 0) or 0)
        session = getattr(connection, "dave_session", None)
        dave = f"v{version}"
        if session is not None:
            counters = []
            speakers = sorted(self.frames, key=self.frames.__getitem__, reverse=True)
            for user_id in speakers + [m for m in members if m not in self.frames]:
                try:
                    stats = session.get_decryption_stats(user_id)
                except Exception:  # davey raises for users it has no decryptor for
                    stats = None
                counters.append(
                    "-"
                    if stats is None
                    else f"{stats.attempts}/{stats.successes}/{stats.failures}/{stats.passthroughs}"
                )
            dave += (
                f" ready={int(bool(getattr(session, 'ready', False)))}"
                f" epoch={getattr(session, 'epoch', None)}"
                f" decrypt(attempts/ok/failed/passthrough)=[{' '.join(counters)}]"
            )
        rates = sorted((n / seconds for n in self.frames.values()), reverse=True)
        counters = {
            name: value - self.patch_before[name]
            for name, value in _patch_counters().items()
        }
        expected = counters["rtp_expected"]
        loss = 1 - counters["rtp_received"] / expected if expected else 0.0
        _LOG.info(
            "voice_receive_stats seconds=%.0f speakers=%d fps=[%s] odd_frames=%d "
            "dropped_no_session=%d decode_errors=%d padded=%d dave_dropped=%d "
            "unknown_ssrc=%d recoveries=%d rtp_packets=%d rtp_loss=%.1f%% dave=%s",
            seconds,
            len(self.frames),
            " ".join(f"{rate:.1f}" for rate in rates),
            self.odd,
            self.dropped,
            counters["decode_errors"],
            counters["padded"],
            counters["dave_dropped"],
            counters["unknown_ssrc"],
            counters["recoveries"],
            counters["rtp_received"],
            100 * max(0.0, loss),
            dave,
        )


def _patch_counters() -> dict[str, int]:
    return {
        name: getattr(voice_recv_patch, name)
        for name in (
            "decode_errors",
            "padded",
            "dave_dropped",
            "unknown_ssrc",
            "recoveries",
            "rtp_expected",
            "rtp_received",
        )
    }
