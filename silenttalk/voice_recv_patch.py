"""Keep one bad Opus frame from stopping voice receive.

voice_recv (upstream + the DAVE receive fix, PR #62) decodes each frame
without a guard: a frame that fails to decode (a key missing for a moment
around a DAVE epoch change, a stray non-audio packet) raises out of the
router thread, which stops listening, and the app then rebuilds the whole
voice connection. Such a frame is decoded as a lost one instead (Opus packet
loss concealment), and counted.
"""

from __future__ import annotations

import logging
from typing import Any

from discord.ext.voice_recv import opus

_LOG = logging.getLogger(__name__)
decode_errors = 0
_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return
    original = getattr(opus.PacketDecoder, "_decode_packet", None)
    if original is None:
        _LOG.warning("voice_recv_patch_skipped reason=no_decode_packet")
        return

    def _decode_packet(self: Any, packet: Any) -> tuple[Any, bytes]:
        global decode_errors
        try:
            return original(self, packet)
        except Exception:  # discord.opus.OpusError, or a malformed payload
            decode_errors += 1
            return packet, self._decoder.decode(None, fec=False)

    opus.PacketDecoder._decode_packet = _decode_packet
    _applied = True
