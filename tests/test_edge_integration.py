from pathlib import Path

import pytest

from silenttalk.config import TTSConfig
from silenttalk.tts.edge import EdgeTTSEngine


@pytest.mark.asyncio
async def test_real_edge_tts_synthesis(tmp_path: Path) -> None:
    engine = EdgeTTSEngine(TTSConfig(timeout_seconds=30), tmp_path)
    await engine.initialize()
    result = await engine.synthesize("等一下，我馬上回來。")
    try:
        assert result.path.stat().st_size > 1_000
        assert result.sample_format == "mp3"
        assert engine.voice.startswith("zh-TW-")
    finally:
        result.path.unlink(missing_ok=True)
        await engine.shutdown()
