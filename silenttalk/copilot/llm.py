from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO

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

    def set_persona(self, persona: Persona) -> None:
        """Takes effect on the next request; the system prompt cache refills once."""
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
    ) -> ReplySuggestions:
        persona = self._persona
        system = self._build_system_prompt(persona)
        prompt = self._build_prompt(
            context=context,
            trigger_speaker=trigger_speaker,
            trigger_text=trigger_text,
            relationships=persona.relationship_notes(context + "\n" + trigger_speaker),
        )
        raw = await asyncio.to_thread(self._request_completion, system, prompt)
        return self._parse_suggestions(raw, trigger_speaker, trigger_text)

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

    def _request_completion(self, system: str, prompt: str) -> str:
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
            "max_tokens": 240,
            "stream": False,
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
        if sheet:
            persona_part = (
                "\n【你的人設】所有候選都必須用這個人的身分、立場、心情和口吻來說：\n"
                f"{sheet}\n"
            )
            self_rule = "關於「你」自己，只能用人設裡寫到的事，不要編新的經歷。"
            example_note = "（範例只示範格式與方向；實際語氣要照你的人設）"
        else:
            persona_part = ""
            self_rule = ""
            example_note = "（範例只示範格式與方向）"
        return f"""你是 Discord 語音聊天的回覆 Copilot，替「你」（使用者本人）想四個可以直接說出口的候選回覆，候選不會自動送出。
{persona_part}
規則：
- 只根據提供的真實對話回應，不得杜撰對方的身分、經歷、情緒或事實。{self_rule}
- 台灣繁體中文口語，每個候選只有一句話，長度{persona.length_rule()}，最長不得超過 {self._max_reply_chars} 字。
- 四個方向固定，內容要彼此不同：
AGREE：同意／順著聊。接受對方的觀點或自然延伸。必須是肯定句，不可以是問句，不可以用問號結尾；不要只說「嗯嗯」「對啊」。
ASK：追問。針對對方剛說的內容問一個具體、自然的問題，必須是問句。
DISAGREE：反對／挑戰。提出不同看法，但不要吵架、羞辱或人身攻擊。
HUMOR：開玩笑／打圓場。用對話裡已有的梗、自嘲或情境反差緩和氣氛。禁止拿外貌、疾病、性別、種族、家庭、收入開玩笑，禁止捏造對方的事。沒有自然又安全的笑點就輸出 SKIP。

範例{example_note}：
{PROMPT_EXAMPLE}

只准輸出 AGREE、ASK、DISAGREE、HUMOR 四行，格式「代號|句子」，不要解釋。"""

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
        return f"""下面是真實 Discord 語音對話（語音辨識結果，可能有錯字、沒有標點）。

{context}
{relation_part}
最後一句：
{trigger_speaker}：{trigger_text}

輸出四行："""

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


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum()).lower()
