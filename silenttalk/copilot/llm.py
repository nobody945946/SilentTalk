from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from silenttalk.copilot.types import ReplySuggestions

_LOG = logging.getLogger(__name__)

_LINE_PATTERN = re.compile(
    r"^\\s*(AGREE|DISAGREE|HUMOR)\\s*[|｜:：]\\s*(.*?)\\s*$",
    re.IGNORECASE,
)
_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


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
    ) -> None:
        self._model_path = model_path
        self._port = port
        self._context_size = context_size
        self._max_reply_chars = max(24, max_reply_chars)
        self._process: subprocess.Popen[bytes] | None = None
        self._base_url = f"http://127.0.0.1:{port}"

    async def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if not self._model_path.is_file():
            raise LocalLLMError(f"找不到 Copilot 模型：{self._model_path}")

        executable = shutil.which("llama-server.exe") or shutil.which("llama-server")
        if not executable:
            raise LocalLLMError(
                "找不到 llama-server.exe；請重新執行「啟動 SilentTalk.cmd」自動部署。"
            )

        threads = max(2, min(6, (os.cpu_count() or 4) // 2))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
            "99",
        ]
        _LOG.info(
            "copilot_llm_start context=%d threads=%d",
            self._context_size,
            threads,
        )
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

        deadline = asyncio.get_running_loop().time() + 30.0
        while asyncio.get_running_loop().time() < deadline:
            if self._process.poll() is not None:
                code = self._process.returncode
                self._process = None
                raise LocalLLMError(f"llama-server 啟動失敗，exit code={code}")
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
        prompt = self._build_prompt(
            context=context,
            trigger_speaker=trigger_speaker,
            trigger_text=trigger_text,
        )
        raw = await asyncio.to_thread(self._request_completion, prompt)
        return self._parse_suggestions(raw, trigger_speaker, trigger_text)

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

    def _request_completion(self, prompt: str) -> str:
        payload = {
            "model": "local",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 Discord 即時聊天回覆 Copilot。"
                        "只替使用者提出短句候選，不代表使用者自動發言。"
                        "必須根據提供的真實對話，不得杜撰對方身分、經歷、情緒或事實。"
                    ),
                },
                {"role": "user", "content": "/no_think\\n" + prompt},
            ],
            "temperature": 0.65,
            "top_p": 0.85,
            "max_tokens": 150,
            "stream": False,
        }
        request = urllib.request.Request(
            self._base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=12.0) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LocalLLMError(f"本機回覆模型失敗：{exc}") from exc

        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMError("本機回覆模型回傳格式異常。") from exc

    def _build_prompt(
        self,
        *,
        context: str,
        trigger_speaker: str,
        trigger_text: str,
    ) -> str:
        return f"""下面是真實 Discord 對話。

{context}

現在最後一句是：
{trigger_speaker}：{trigger_text}

請產生三個「方向固定、內容不同」的繁體中文短回覆。每句最好 8～30 字，最長不得超過 {self._max_reply_chars} 字。

AGREE：同意／順著聊。接受對方核心觀點，或自然延伸；不要只是「嗯嗯」「對啊」。
DISAGREE：反對／挑戰。提出不同看法或疑問，但不要變成吵架、羞辱或人身攻擊。
HUMOR：開他玩笑／打圓場。優先使用對話裡已存在的梗、輕微自嘲、情境反差來緩和氣氛。禁止拿外貌、疾病、性別、種族、家庭、收入等敏感或私人特徵開玩笑；禁止憑空捏造對方的事。若沒有自然且低風險的笑點，輸出 SKIP，不要硬講爛梗。

只准輸出以下三行，不要解釋：
AGREE|...
DISAGREE|...
HUMOR|..."""

    def _parse_suggestions(
        self,
        raw: str,
        trigger_speaker: str,
        trigger_text: str,
    ) -> ReplySuggestions:
        cleaned = _THINK_PATTERN.sub("", raw).strip()
        values: dict[str, str] = {"AGREE": "", "DISAGREE": "", "HUMOR": ""}
        for line in cleaned.splitlines():
            match = _LINE_PATTERN.match(line)
            if not match:
                continue
            key = match.group(1).upper()
            value = self._clean_reply(match.group(2))
            if value.upper() == "SKIP":
                value = ""
            values[key] = value

        return ReplySuggestions(
            trigger_speaker=trigger_speaker,
            trigger_text=trigger_text,
            agree=values["AGREE"],
            disagree=values["DISAGREE"],
            humor=values["HUMOR"],
        )

    def _clean_reply(self, value: str) -> str:
        value = value.strip().strip("\"'「」『』")
        value = " ".join(value.split())
        if len(value) > self._max_reply_chars:
            value = value[: self._max_reply_chars].rstrip() + "…"
        return value
