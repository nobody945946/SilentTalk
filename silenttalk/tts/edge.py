from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import aiohttp
import edge_tts

from silenttalk.config import TTSConfig
from silenttalk.speech_settings import combine_edge_rate, validate_rate_multiplier
from silenttalk.tts.base import AudioResult
from silenttalk.tts.stream import AudioStream
from silenttalk.voice_styles import VOICE_STYLES, VoiceStyle

_LOG = logging.getLogger(__name__)

# Microsoft moved Edge's read-aloud synthesis to api.msedgeservices.com: from
# 2026-10-10 the old address answers every handshake with 403, region by
# region (rany2/edge-tts#490), and edge-tts 7.2.8, the latest, still uses it.
# The new address takes the same client token and Sec-MS-GEC (the newer
# Sec-MS-GEC-Version is refused there). Voices still list at the old one.
# tests/test_tts_edge.py fails once edge-tts ships the new address itself.
SYNTHESIS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    f"?Ocp-Apim-Subscription-Key={edge_tts.constants.TRUSTED_CLIENT_TOKEN}"
)
edge_tts.communicate.WSS_URL = SYNTHESIS_URL

# The service turning a handshake away as busy (2026-10-12: the new address
# answered 429 to 1 of 3 requests in a burst) costs the line unless it is
# asked again; nothing has played yet, so one more try is safe.
_BUSY_STATUS = {429, 503}
_BUSY_RETRY_SECONDS = 0.3


async def _audio(make: Callable[[], edge_tts.Communicate]) -> AsyncIterator[bytes]:
    """One request's MP3 chunks; a busy handshake is tried once more."""
    for attempt in (0, 1):
        try:
            async for chunk in make().stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
            return
        except aiohttp.WSServerHandshakeError as exc:
            if attempt or exc.status not in _BUSY_STATUS:
                raise
            _LOG.warning("edge_tts_busy status=%s retrying", exc.status)
            await asyncio.sleep(_BUSY_RETRY_SECONDS)

# speech.platform.bing.com resolves to IPv6 first; where IPv6 does not get
# through, aiohttp's default 250 ms happy-eyeballs delay was added to 5 of 12
# requests on the dev box (first audio 352 ms median -> 244 ms, 0 slow runs
# with 50 ms). IPv6 is still tried first.
_HAPPY_EYEBALLS_DELAY = 0.05


def _connector() -> aiohttp.TCPConnector:
    # One per request: the session edge_tts opens owns and closes it.
    return aiohttp.TCPConnector(happy_eyeballs_delay=_HAPPY_EYEBALLS_DELAY)


def _consume_legacy_style_prefix(text: str, voice_style: str) -> tuple[str, str]:
    """Keep old /deep, /space_marine, etc. inputs working without using them internally."""
    stripped = text.lstrip()
    prefix, separator, remainder = stripped.partition(" ")
    if not prefix.startswith("/") or not separator or not remainder.strip():
        return text, voice_style

    key = prefix[1:].lower()
    if key not in VOICE_STYLES:
        return text, voice_style
    return remainder.strip(), key


def resolve_speech_settings(
    text: str,
    config: TTSConfig,
    voice_style: str | VoiceStyle = "default",
    rate_multiplier: float = 1.0,
) -> tuple[str, str, str, str, str, str | None]:
    """Resolve text + structured style + UI speed into EdgeTTS/FFmpeg settings.

    `voice_style` is a VOICE_STYLES key, or a persona's own VoiceStyle."""
    validate_rate_multiplier(rate_multiplier)
    if isinstance(voice_style, VoiceStyle):
        spoken_text, style = text, voice_style
    else:
        spoken_text, style_key = _consume_legacy_style_prefix(text, voice_style)
        style = VOICE_STYLES.get(style_key)
        if style is None:
            raise ValueError(f"未知聲線：{style_key}")

    if style.key == "default":
        voice = config.voice
        base_rate = config.rate
        pitch = config.pitch
        volume = config.volume
    else:
        voice = style.voice or config.voice
        base_rate = style.rate
        pitch = style.pitch
        volume = style.volume

    rate = combine_edge_rate(base_rate, rate_multiplier)
    return spoken_text, voice, rate, pitch, volume, style.ffmpeg_filter


class EdgeTTSEngine:
    def __init__(self, config: TTSConfig, temp_dir: Path) -> None:
        self._config = config
        self._temp_dir = temp_dir
        self._voice = config.voice

    @property
    def voice(self) -> str:
        return self._voice

    def apply_config(self, config: TTSConfig) -> None:
        """Voice and the global rate/pitch/volume tweaks, changed live."""
        self._config = config
        if config.voice:
            self._voice = config.voice

    async def initialize(self) -> None:
        if self._voice:
            return
        voices = await asyncio.wait_for(
            edge_tts.list_voices(), timeout=self._config.timeout_seconds
        )
        candidates = [v for v in voices if str(v.get("Locale", "")).lower() == "zh-tw"]
        if not candidates:
            raise RuntimeError("EdgeTTS 沒有回傳 zh-TW voice。")
        female = next(
            (v for v in candidates if v.get("Gender") == "Female"), candidates[0]
        )
        self._voice = str(female["ShortName"])
        _LOG.info("edge_tts_voice_selected voice=%s", self._voice)

    async def stream(
        self,
        text: str,
        voice_style: str | VoiceStyle = "default",
        rate_multiplier: float = 1.0,
    ) -> AudioResult:
        """Like synthesize(), but returns as soon as the first MP3 chunk is in;
        the rest keeps arriving in `AudioResult.stream`. Nothing is written to
        disk."""
        spoken_text, voice, rate, pitch, volume, audio_filter = await self._settings(
            text, voice_style, rate_multiplier
        )
        def make() -> edge_tts.Communicate:
            return edge_tts.Communicate(
                spoken_text, voice, rate=rate, volume=volume, pitch=pitch,
                connector=_connector(),
            )

        def chunks() -> AsyncIterator[bytes]:
            return _audio(make)

        stream = AudioStream()
        await stream.start(chunks, first_chunk_timeout=self._config.timeout_seconds)
        return AudioResult(
            None, None, None, "mp3", ffmpeg_filter=audio_filter, stream=stream
        )

    async def _settings(
        self, text: str, voice_style: str | VoiceStyle, rate_multiplier: float
    ) -> tuple[str, str, str, str, str, str | None]:
        if not self._voice:
            await self.initialize()
        effective_config = TTSConfig(
            engine=self._config.engine,
            voice=self._voice,
            rate=self._config.rate,
            pitch=self._config.pitch,
            volume=self._config.volume,
            timeout_seconds=self._config.timeout_seconds,
        )
        return resolve_speech_settings(
            text,
            effective_config,
            voice_style=voice_style,
            rate_multiplier=rate_multiplier,
        )

    async def synthesize(
        self,
        text: str,
        voice_style: str | VoiceStyle = "default",
        rate_multiplier: float = 1.0,
    ) -> AudioResult:
        spoken_text, voice, rate, pitch, volume, audio_filter = await self._settings(
            text, voice_style, rate_multiplier
        )

        fd, raw_path = tempfile.mkstemp(
            prefix="silenttalk-", suffix=".mp3", dir=self._temp_dir
        )
        import os

        os.close(fd)
        path = Path(raw_path)
        def make() -> edge_tts.Communicate:
            return edge_tts.Communicate(
                spoken_text, voice, rate=rate, volume=volume, pitch=pitch,
                connector=_connector(),
            )

        async def write() -> None:
            with path.open("wb") as handle:
                async for data in _audio(make):
                    handle.write(data)

        try:
            await asyncio.wait_for(write(), timeout=self._config.timeout_seconds)
            if path.stat().st_size == 0:
                raise RuntimeError("EdgeTTS 產生空白音訊。")
            return AudioResult(
                path, None, None, "mp3", ffmpeg_filter=audio_filter
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def shutdown(self) -> None:
        return None
