from __future__ import annotations

import asyncio
import collections
import dataclasses
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import IO

from silenttalk.copilot.character import asks_if_ai
from silenttalk.copilot.persona import Persona, blank_persona
from silenttalk.copilot.script import to_taiwan_traditional
from silenttalk.copilot.types import REPLY_LANES, ReplySuggestions

_LOG = logging.getLogger(__name__)

# One worked example teaches the four-line format and keeps AGREE from
# drifting into questions (0.50 -> 0.00 on scripts/dev/llm_eval.py). It must not
# resemble LLM_SCENES, and its lines must not have a reusable sentence pattern:
# a "你這不是X，是Y吧" joke got copied into 15 of 24 HUMOR replies.
PROMPT_EXAMPLE_LINES = (
    ("AGREE", "熬到四點真的會廢，今天一定要早點睡"),
    ("ASK", "什麼劇這麼好看，能讓你撐到四點？"),
    ("DISAGREE", "上班日還熬到四點，這樣身體會撐不住啦"),
    ("HUMOR", "今天的咖啡應該要直接點特大杯了"),
)
PROMPT_EXAMPLE = "對話：\n阿明：我昨天熬夜追劇追到四點\n阿明：今天上班整個廢掉\n輸出：\n" + "\n".join(
    f"{code}|{text}" for code, text in PROMPT_EXAMPLE_LINES
)

_NEUTRAL_SYSTEM = """你是 Discord 語音聊天的回覆 Copilot，替「你」（使用者本人）想四個可以直接說出口的候選回覆，候選不會自動送出。

規則：
- 只根據提供的真實對話回應，不得杜撰對方的身分、經歷、情緒或事實。
- 台灣繁體中文口語，每個候選只有一句話，長度{length}，最長不得超過 {max_chars} 字。
- 四個方向固定，內容要彼此不同：
AGREE：同意／順著聊。接受對方的觀點或自然延伸。必須是肯定句，不可以是問句，不可以用問號結尾；不要只說「嗯嗯」「對啊」。
ASK：追問。針對對方剛說的內容問一個具體、自然的問題，必須是問句。
DISAGREE：反對／挑戰。提出不同看法，但不要吵架、羞辱或人身攻擊。
HUMOR：開玩笑／打圓場。用對話裡已有的梗、自嘲或情境反差緩和氣氛。禁止拿外貌、疾病、性別、種族、家庭、收入開玩笑，禁止捏造對方的事。沒有自然又安全的笑點就輸出 SKIP。

範例（範例只示範格式與方向）：
{example}

只准輸出 AGREE、ASK、DISAGREE、HUMOR 四行，格式「代號|句子」，不要解釋。"""

# With a persona every lane is taken from the character's own stance: AGREE may
# not endorse what the character would never say, and any lane may SKIP. The
# sheet comes last, closest to the answer, where a small model attends most.
_PERSONA_SYSTEM = """你是 Discord 語音聊天的回覆 Copilot，替「你」想四個可以直接說出口的候選回覆，候選不會自動送出。「你」是下面人設裡的這個人，四句都要是這個人真的會說的話。

規則：
- 只根據提供的真實對話回應，不得杜撰對方的身分、經歷、情緒或事實。關於「你」自己，只能用人設裡寫到的事，不要編新的經歷，也不要說自己是 AI。
- 台灣繁體中文口語，每個候選只有一句話，長度{length}，最長不得超過 {max_chars} 字。
- 四個方向固定，內容要彼此不同，而且都站在「你」的立場：
AGREE：順著聊。用你的立場接住對方的話或自然延伸，必須是肯定句，不可以用問號結尾。對方的話違反你的價值觀或底線時，只同意你真的能同意的部分。
ASK：追問。針對對方剛說的內容問一個具體、自然的問題，必須是問句。
DISAGREE：反對／挑戰。依你的價值觀提出不同看法，但不要吵架、羞辱或人身攻擊。
HUMOR：開玩笑／打圓場。用你的幽默風格和對話裡已有的梗緩和氣氛。禁止拿外貌、疾病、性別、種族、家庭、收入開玩笑，禁止捏造對方的事。
- 任何一個方向，如果你這個人設不會這樣說，就輸出 SKIP。

範例（只示範格式與方向，語氣要照你的人設）：
{example}

【你的人設】口吻、用詞、句長、立場都照這裡：
{sheet}

只准輸出 AGREE、ASK、DISAGREE、HUMOR 四行，格式「代號|句子」，不要解釋。"""

# Character mode: the bot itself is the character and speaks one line aloud
# with nobody approving it first, so it may stay silent (SKIP) and must not
# pretend to be human when sincerely asked.
_CHARACTER_SYSTEM = """你是 Discord 語音頻道裡的一個角色 Bot，由 AI 扮演{who}，和大家一起用語音聊天。你說的話會直接用語音播出來。

規則：
- 只根據真實對話回應，不得杜撰別人的身分、經歷、情緒或事實。關於你自己，只用人設裡寫到的事，不要編新的經歷。
- 你是 AI 扮演的角色：平常用角色口吻聊天；有人認真問你是不是 AI、機器人或真人時，要誠實承認你是 AI 角色（可以用角色口吻說）。
- 你只存在於這個語音頻道，只能用嘴巴聊天：不能打字、寫程式、寫文章、翻譯整段文字、上網查資料、設提醒，也不會記得下次聊天。被要求做這些事時，用這個角色會有的方式回應（推託、吐槽、給一句口頭建議、叫對方自己來或用別的工具），絕對不要答應或假裝在做你做不到的事。
- 你不是百科全書：超出你人設會懂的問題，就用這個人真實的程度回答，可以說不知道。
- 台灣繁體中文口語，只說一句話，長度{length}，最長不得超過 {max_chars} 字。
- 像朋友聊天一樣自然接話：附和、追問、吐槽或開玩笑，選這個角色此刻最可能的反應。不要重複別人的話，不要說教，不要每句都叫對方名字。
- 不羞辱、不人身攻擊，不拿外貌、疾病、性別、種族、家庭、收入開玩笑。
- 這時候插話不自然（別人在私下聊、話題跟你無關、你剛說過類似的話）就輸出 SKIP。
{sheet}
只輸出一行：你要說的話，或 SKIP。不要加引號、名字或解釋。"""

_END_PUNCTUATION = "？?！!。.…~～」』)）"
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
# llama-server stderr lines worth keeping in the app log: they prove whether
# the model actually landed on the GPU. Conversation text never appears here.
_DIAGNOSTIC_MARKERS = ("offloaded", "using device", "error", "failed", "out of memory")


class LocalLLMError(RuntimeError):
    pass


class LocalReplyModel:
    """Persistent llama.cpp server for tiny local reply generation."""

    def __init__(
        self,
        model_path: Path,
        *,
        port: int = 18088,
        context_size: int = 2048,
        max_reply_chars: int = 72,
        gpu_layers: int = 99,
        request_timeout_seconds: float = 15.0,
        low_vram: bool = True,
    ) -> None:
        self._model_path = model_path
        self._port = port
        self._context_size = context_size
        self._max_reply_chars = max(24, max_reply_chars)
        self._gpu_layers = max(0, gpu_layers)
        self._low_vram = low_vram
        self._request_timeout = max(3.0, request_timeout_seconds)
        self._process: subprocess.Popen[bytes] | None = None
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=40)
        self._base_url = f"http://127.0.0.1:{port}"
        self._persona = blank_persona()
        # What the character said lately, to stop it repeating its catchphrases.
        self._recent_character_lines: collections.deque[str] = collections.deque(maxlen=4)

    def set_persona(self, persona: Persona) -> None:
        """Takes effect on the next request; the system prompt cache refills once."""
        if persona.id != self._persona.id:
            self._recent_character_lines.clear()
        self._persona = persona

    async def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if not self._model_path.is_file():
            raise LocalLLMError(f"找不到 Copilot 模型：{self._model_path}")

        executable = find_llama_server()

        threads = max(2, min(6, (os.cpu_count() or 4) // 2))
        devices = await asyncio.to_thread(list_llama_devices, executable)
        _LOG.info("copilot_llm_devices %s", " | ".join(devices) or "none(cpu-only)")
        args = [
            executable,
            "--model",
            str(self._model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--ctx-size",
            str(self._context_size),
            "--threads",
            str(threads),
            "--n-gpu-layers",
            str(self._gpu_layers),
            # One slot: recent llama-server defaults to several parallel slots,
            # which splits the context and competes for a 4 GB laptop GPU.
            "--parallel",
            "1",
            # Needed so chat_template_kwargs.enable_thinking reaches Qwen3's template.
            "--jinja",
        ]
        _LOG.info(
            "copilot_llm_start model=%s context=%d threads=%d gpu_layers=%d low_vram=%s",
            self._model_path.name,
            self._context_size,
            threads,
            self._gpu_layers,
            self._low_vram,
        )
        if self._low_vram:
            # 8-bit KV cache: 1.7B at ctx 4096 drops from ~1.6 GB to ~1.4 GB of
            # VRAM, which matters next to a game on a 4 GB card. Quantized V
            # needs flash attention; drivers without it fall back to f16.
            try:
                await self._launch(
                    args + ["--flash-attn", "on"]
                    + ["--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]
                )
                return
            except LocalLLMError as exc:
                _LOG.warning("copilot_llm_low_vram_fallback reason=%s", str(exc)[:160])
        await self._launch(args)

    async def _launch(self, args: list[str]) -> None:
        self._stderr_tail.clear()
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if self._process.stderr is not None:
            threading.Thread(
                target=self._drain_stderr,
                args=(self._process.stderr,),
                name="copilot-llm-stderr",
                daemon=True,
            ).start()

        deadline = asyncio.get_running_loop().time() + 60.0
        while asyncio.get_running_loop().time() < deadline:
            if self._process.poll() is not None:
                code = self._process.returncode
                self._process = None
                raise LocalLLMError(
                    f"llama-server 啟動失敗，exit code={code}｜{self._last_error_line()}"
                )
            if await asyncio.to_thread(self._health_ok):
                return
            await asyncio.sleep(0.25)

        await self.stop()
        raise LocalLLMError("llama-server 載入模型逾時。")

    async def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, 3)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)

    async def suggest(
        self,
        *,
        context: str,
        trigger_speaker: str,
        trigger_text: str,
        on_partial: Callable[[ReplySuggestions], None] | None = None,
    ) -> ReplySuggestions:
        """Four reply lanes. With `on_partial`, each lane is also reported as
        soon as its line is complete (called from a worker thread), so a slow
        laptop GPU shows the first choice long before the fourth is written."""
        persona = self._persona
        system = self._build_system_prompt(persona)
        prompt = self._build_prompt(
            context=context,
            trigger_speaker=trigger_speaker,
            trigger_text=trigger_text,
            relationships=persona.relationship_notes(context + "\n" + trigger_speaker),
        )
        if on_partial is None:
            raw = await asyncio.to_thread(self._request_completion, system, prompt)
            return self._parse_suggestions(raw, trigger_speaker, trigger_text)

        shown = 0

        def on_lines(text: str) -> None:
            nonlocal shown
            partial = self._parse_suggestions(text, trigger_speaker, trigger_text)
            filled = sum(bool(value) for _, value in partial.items())
            if filled > shown:
                shown = filled
                on_partial(dataclasses.replace(partial, partial=True))

        raw = await asyncio.to_thread(self._request_completion, system, prompt, on_lines)
        return self._parse_suggestions(raw, trigger_speaker, trigger_text)

    async def character_reply(
        self,
        *,
        context: str,
        trigger_speaker: str,
        trigger_text: str,
        addressed: bool = False,
    ) -> str:
        """One line the character says aloud, or "" when it should stay quiet."""
        system = self._build_character_system_prompt(self._persona)
        prompt = self._build_character_prompt(
            context=context,
            trigger_speaker=trigger_speaker,
            trigger_text=trigger_text,
            addressed=addressed,
        )
        raw = await asyncio.to_thread(
            self._request_completion, system, prompt, None, 90
        )
        line = self._parse_character_line(raw, trigger_text)
        if line:
            self._recent_character_lines.append(line)
        return line

    def _build_character_prompt(
        self,
        *,
        context: str,
        trigger_speaker: str,
        trigger_text: str,
        addressed: bool,
    ) -> str:
        persona = self._persona
        relationships = persona.relationship_notes(context + "\n" + trigger_speaker)
        relation_part = ""
        if relationships:
            relation_part = "\n你和在場的人的關係：\n" + "\n".join(
                f"- {note}" for note in relationships
            ) + "\n"
        addressed_part = "（對方是在跟你說話，要回應）\n" if addressed else ""
        reminder = ""
        if not persona.is_blank:
            reminder = persona.reminder_line("這句要是", list_catchphrases=False) + "\n"
        used = [
            phrase
            for phrase in persona.signature_phrases()
            if any(_signature_used(phrase, line) for line in self._recent_character_lines)
        ]
        if used:
            reminder += (
                "（你最近已經說過" + "、".join(f"「{p}」" for p in used[:3])
                + "，這句換個說法，不要再用）\n"
            )
        # Small models ignore the honesty rule under persona pressure ("欸我不
        # 是AI啦"); when the chat is actually asking, say so right here.
        recent = "\n".join(context.splitlines()[-3:] + [trigger_text])
        if asks_if_ai(recent):
            reminder += "（有人在問你是不是 AI 或真人：要老實承認你是 AI 扮演的角色，用你的口吻說）\n"
        return f"""下面是真實 Discord 語音對話（語音辨識結果，可能有錯字、沒有標點）。「你」是你自己之前說過的話。

{context}
{relation_part}
最後一句：
{trigger_speaker}：{trigger_text}
{addressed_part}
{reminder}你要說："""

    def _build_character_system_prompt(self, persona: Persona) -> str:
        sheet = persona.render_system_block()
        return _CHARACTER_SYSTEM.format(
            who="下面人設裡的人" if sheet else "一個友善、好聊的朋友",
            length=persona.length_rule(),
            max_chars=self._max_reply_chars,
            sheet=f"\n【你的人設】口吻、用詞、句長、立場都照這裡：\n{sheet}\n" if sheet else "",
        )

    def _parse_character_line(self, raw: str, trigger_text: str) -> str:
        cleaned = raw.strip()
        close_index = cleaned.lower().rfind(_THINK_CLOSE)
        if close_index >= 0:
            cleaned = cleaned[close_index + len(_THINK_CLOSE) :]
        line = next((part.strip() for part in cleaned.splitlines() if part.strip()), "")
        # Tolerate "SAY|…", "你要說：…" and "<own name>：…" decorations, but
        # never strip other text before a colon ("說真的：…" is speech).
        names = {"你", "我", self._persona.name.strip()} | {
            nick.strip() for nick in self._persona.nickname.split("、")
        }
        speaker = "|".join(re.escape(name) for name in names if name)
        line = re.sub(rf"^(SAY\s*[|｜:：]|你要說\s*[:：]|({speaker})\s*[:：])", "", line).strip()
        value = self._clean_reply(line)
        if not value or value.upper().startswith("SKIP") or _compact(value) == _compact(trigger_text):
            return ""
        return value

    def _drain_stderr(self, stream: IO[bytes]) -> None:
        for raw_line in iter(stream.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            self._stderr_tail.append(line)
            lower = line.lower()
            if any(marker in lower for marker in _DIAGNOSTIC_MARKERS):
                _LOG.info("copilot_llm_server %s", line[:300])
        stream.close()

    def _last_error_line(self) -> str:
        for line in reversed(self._stderr_tail):
            lower = line.lower()
            if "error" in lower or "failed" in lower or "memory" in lower:
                return line[:200]
        return self._stderr_tail[-1][:200] if self._stderr_tail else "沒有輸出"

    def _health_ok(self) -> bool:
        try:
            request = urllib.request.Request(
                self._base_url + "/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=1.0) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError):
            return False

    def _request_completion(
        self,
        system: str,
        prompt: str,
        on_lines: Callable[[str], None] | None = None,
        max_tokens: int = 240,
    ) -> str:
        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": "/no_think\n" + prompt},
            ],
            # The system prompt is identical across requests; reuse its KV cache.
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0.65,
            "top_p": 0.85,
            "max_tokens": max_tokens,
            "stream": on_lines is not None,
        }
        request = urllib.request.Request(
            self._base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._request_timeout
            ) as response:
                if on_lines is not None:
                    return consume_stream(response, on_lines)
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LocalLLMError(f"本機回覆模型失敗：{exc}") from exc

        try:
            return str(body["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMError("本機回覆模型回傳格式異常。") from exc

    def _build_system_prompt(self, persona: Persona) -> str:
        """Everything that does not change between requests: role, persona, rules.

        Kept byte-stable so llama-server reuses its KV cache; on a 4 GB laptop
        GPU that turns a long persona into a one-time cost.
        """
        sheet = persona.render_system_block()
        if not sheet:
            return _NEUTRAL_SYSTEM.format(
                length=persona.length_rule(),
                max_chars=self._max_reply_chars,
                example=PROMPT_EXAMPLE,
            )
        return _PERSONA_SYSTEM.format(
            length=persona.length_rule(),
            max_chars=self._max_reply_chars,
            example=PROMPT_EXAMPLE,
            sheet=sheet,
        )

    def _build_prompt(
        self,
        *,
        context: str,
        trigger_speaker: str,
        trigger_text: str,
        relationships: list[str] | None = None,
    ) -> str:
        relation_part = ""
        if relationships:
            relation_part = (
                "\n你和在場的人的關係：\n"
                + "\n".join(f"- {note}" for note in relationships)
                + "\n"
            )
        reminder = ""
        if not self._persona.is_blank:
            # Small models drift toward a neutral voice over a long transcript;
            # restating who is talking right before the answer holds the
            # character (persona_eval.py: voice 3.31 -> 3.64 on Qwen3-4B-2507).
            reminder = self._persona.reminder_line() + "\n"
        return f"""下面是真實 Discord 語音對話（語音辨識結果，可能有錯字、沒有標點）。

{context}
{relation_part}
最後一句：
{trigger_speaker}：{trigger_text}

{reminder}輸出四行："""

    def _parse_suggestions(
        self,
        raw: str,
        trigger_speaker: str,
        trigger_text: str,
    ) -> ReplySuggestions:
        cleaned = raw.strip()
        lower = cleaned.lower()
        open_index = lower.find(_THINK_OPEN)
        close_index = lower.rfind(_THINK_CLOSE)
        if open_index >= 0 and close_index >= open_index:
            cleaned = (
                cleaned[:open_index] + cleaned[close_index + len(_THINK_CLOSE) :]
            ).strip()

        echo = _compact(trigger_text)
        values: dict[str, str] = {lane.field: "" for lane in REPLY_LANES}
        for line in cleaned.splitlines():
            # Small models like to decorate: "1. **AGREE**｜…", "- ASK: …".
            stripped = line.strip().lstrip("-*•#>0123456789.、) ").strip()
            upper = stripped.upper()
            for lane in REPLY_LANES:
                if not upper.startswith(lane.code):
                    continue
                remainder = stripped[len(lane.code) :].lstrip(" *|｜:：").strip()
                value = self._clean_reply(remainder)
                if value.upper() == "SKIP" or _compact(value) == echo:
                    value = ""
                elif lane.code == "ASK" and value and value[-1] not in _END_PUNCTUATION:
                    # Gemma often drops the question mark; TTS needs it to
                    # say the line with a rising, questioning tone.
                    value += "？"
                values[lane.field] = value
                break

        return ReplySuggestions(
            trigger_speaker=trigger_speaker,
            trigger_text=trigger_text,
            **values,
        )

    def _clean_reply(self, value: str) -> str:
        value = value.strip().strip("\"'「」『』*")
        # Small Qwen models slip into Simplified now and then (2-9% of lanes).
        value = to_taiwan_traditional(" ".join(value.split()))
        if value.startswith("...") or value in {"…", "..."}:
            return ""
        if len(value) > self._max_reply_chars:
            value = value[: self._max_reply_chars].rstrip() + "…"
        return value


def consume_stream(events: Iterable[bytes], on_lines: Callable[[str], None]) -> str:
    """Read an OpenAI-style SSE stream; call `on_lines(text so far)` whenever a
    line is complete. Returns the whole text."""
    text = ""
    for raw in events:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            choice = json.loads(data)["choices"][0]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            continue
        piece = (choice.get("delta") or {}).get("content") or ""
        if not piece:
            continue
        text += piece
        if "\n" in piece:
            on_lines(text[: text.rfind("\n")])
    return text


def find_llama_server() -> str:
    executable = shutil.which("llama-server.exe") or shutil.which("llama-server")
    if not executable:
        raise LocalLLMError(
            "找不到 llama-server.exe；請重新執行「啟動 SilentTalk.cmd」自動部署。"
        )
    return executable


def list_llama_devices(executable: str) -> list[str]:
    """GPUs llama.cpp can use, e.g. "Vulkan0: NVIDIA GeForce RTX 3050 Ti (4096 MiB, …)".

    An empty list means the model will run on the CPU (about 3x slower).
    """
    try:
        listing = subprocess.run(
            [executable, "--list-devices"],
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    output = (listing.stdout + listing.stderr).decode("utf-8", errors="replace")
    return [
        line.strip() for line in output.splitlines() if "MiB" in line and ":" in line
    ]


def _signature_used(phrase: str, line: str) -> bool:
    """A catchphrase appears, or a long sample line is echoed in part."""
    phrase, line = _compact(phrase), _compact(line)
    if len(phrase) <= 6:
        return bool(phrase) and phrase in line
    return any(phrase[i : i + 5] in line for i in range(len(phrase) - 4))


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum()).lower()
