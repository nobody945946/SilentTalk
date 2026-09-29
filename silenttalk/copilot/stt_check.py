"""Real-voice STT check: the owner reads fixed sentences in the voice channel.

`python app.py --stt-check` joins the owner's voice channel the way the app
does and listens only to the owner. The console shows one sentence at a
time; what the local STT heard is scored against it (character error rate).
Transcripts stay in memory: only rates and counts are printed and logged,
so nobody has to judge transcripts by eye. The voice_receive_stats and
copilot_stt_segment lines logged meanwhile tell where a failure comes from
(frames not decrypted, audio that looks like noise, or the recogniser).
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from pathlib import Path

from silenttalk.config import Settings
from silenttalk.copilot.smoke import (
    STT_MAX_CER,
    STT_SENTENCES,
    build_transcriber,
    char_error_rate,
)
from silenttalk.discord_voice import DiscordVoiceClient
from silenttalk.state import AppState

_LOG = logging.getLogger(__name__)

CHECK_SENTENCES = STT_SENTENCES + (
    "今天晚上七點半在老地方集合",
    "我覺得這把我們應該先守一下",
    "阿傑你那邊還有幾個人",
)
SENTENCE_TIMEOUT = 20.0


async def run_stt_check(settings: Settings, project_dir: Path) -> bool:
    owner = settings.discord.owner_user_id
    transcriber, collector = build_transcriber(project_dir, settings.copilot)

    def on_pcm(user_id: int, name: str, pcm: bytes) -> None:
        if user_id == owner:
            transcriber.push_pcm(user_id, name, pcm)

    def status(state: AppState, message: str) -> None:
        print(f"{state.value}: {message}")

    _LOG.info("copilot_stt_check_start sentences=%d", len(CHECK_SENTENCES))
    await asyncio.to_thread(transcriber.start)
    client = DiscordVoiceClient(settings.discord, status, pcm_callback=on_pcm)
    rates: list[float] = []
    try:
        async with client:
            await client.login(settings.discord.token)
            connect_task = asyncio.create_task(client.connect(reconnect=False))
            try:
                await asyncio.wait_for(client.wait_until_ready(), timeout=30)
                print("請先進 Discord 語音頻道；Bot 會跟著進來。")
                await _wait_listening(client, timeout=120)
                # Let the DAVE handshake settle before the first sentence.
                await asyncio.sleep(3)
                print(
                    f"\n接下來會一句一句顯示 {len(CHECK_SENTENCES)} 句話。"
                    "看到就用平常的速度念出來，念完等下一句。\n"
                )
                for index, sentence in enumerate(CHECK_SENTENCES, 1):
                    collector.reset()
                    print(f"[{index}/{len(CHECK_SENTENCES)}] 請念：{sentence}")
                    heard = await asyncio.to_thread(collector.wait, SENTENCE_TIMEOUT)
                    rate = char_error_rate(sentence, heard) if heard else 1.0
                    rates.append(rate)
                    _LOG.info(
                        "copilot_stt_check index=%d cer=%.3f heard_chars=%d",
                        index,
                        rate,
                        len(heard),
                    )
                    print(
                        f"    錯字率 {rate:.0%}（聽到 {len(heard)} 字）"
                        if heard
                        else f"    {SENTENCE_TIMEOUT:.0f} 秒內沒有辨識結果"
                    )
                    await asyncio.sleep(1.0)
            finally:
                await client.close()
                await asyncio.gather(connect_task, return_exceptions=True)
    finally:
        await asyncio.to_thread(transcriber.stop)
    average = statistics.fmean(rates) if rates else 1.0
    heard_count = sum(rate < 1.0 for rate in rates)
    passed = bool(rates) and average <= STT_MAX_CER
    _LOG.info(
        "copilot_stt_check_done sentences=%d cer=%.3f passed=%d",
        len(rates),
        average,
        int(passed),
    )
    print(
        f"\n平均錯字率 {average:.1%}（門檻 {STT_MAX_CER:.0%}），"
        f"{heard_count}/{len(rates)} 句有結果 → {'PASS' if passed else 'FAIL'}"
    )
    return passed


async def _wait_listening(client: DiscordVoiceClient, timeout: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        voice = client.active_voice()
        if voice is not None and getattr(voice, "is_listening", lambda: False)():
            return
        if loop.time() >= deadline:
            raise RuntimeError(f"{timeout:.0f} 秒內沒有開始收音（Bot 沒進語音頻道？）")
        await asyncio.sleep(0.5)
