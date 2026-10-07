from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

from silenttalk.agent_lease import CharacterLease
from silenttalk.copilot import reply_templates as templates


class LocalLLMError(RuntimeError):
    """The independent reply service did not provide a usable response."""


class ReplyTransport:
    def __init__(self, project_dir: Path, port: int, adapter: bool, timeout: float):
        self.base_url = f"http://127.0.0.1:{port}"
        self.adapter_loaded = False
        self._adapter = adapter
        self.timeout_seconds = max(3.0, timeout)
        self.lease = CharacterLease(project_dir, os.getpid(), self._connected)

    def _connected(self, lease: dict[str, object]) -> None:
        port = lease.get("port")
        if type(port) is int and 1024 <= port <= 65535:
            self.base_url = f"http://127.0.0.1:{port}"
        self.adapter_loaded = self._adapter

    async def start(self) -> None:
        await self.lease.start()

    async def stop(self) -> None:
        try:
            await self.lease.stop()
        finally:
            self.adapter_loaded = False

    def health_ok(self) -> bool:
        try:
            request = urllib.request.Request(
                self.base_url + "/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=1.0) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError):
            return False

    def request_completion(
        self,
        system: str,
        prompt: str,
        on_lines: Callable[[str], None] | None = None,
        max_tokens: int = 240,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "/no_think\n" + prompt},
        ]
        return self.request_messages(messages, on_lines, max_tokens)

    def request_gate(
        self, messages: list[dict[str, str]], character: bool = True
    ) -> str:
        payload = {
            "model": "local",
            "messages": messages,
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "grammar": templates._GATE_GRAMMAR,
            "temperature": 0.0,
            "max_tokens": 1,
            **self.lora_field(character),
        }
        body = self._post(payload)
        try:
            return str(body["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMError("本機回覆模型回傳格式異常。") from exc

    def _post(self, payload: dict[str, object]) -> dict:
        request = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LocalLLMError(f"本機回覆模型失敗：{exc}") from exc

    def lora_field(self, character: bool) -> dict[str, object]:
        """Every request sets the adapter's scale (llama-server applies a
        loaded adapter to requests that leave it out) and the slot kept for
        that scale, so switching does not throw away the other's cache."""
        if not self.adapter_loaded:
            return {"id_slot": 0}
        return {
            "lora": [{"id": 0, "scale": 1.0 if character else 0.0}],
            "id_slot": 0 if character else 1,
        }

    def request_messages(
        self,
        messages: list[dict[str, str]],
        on_lines: Callable[[str], None] | None = None,
        max_tokens: int = 240,
        character: bool = False,
        temperature: float = 0.65,
    ) -> str:
        payload = {
            "model": "local",
            **self.lora_field(character),
            "messages": messages,
            # The system prompt is identical across requests; reuse its KV cache.
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": temperature,
            "top_p": 0.85,
            "max_tokens": max_tokens,
            "stream": on_lines is not None,
        }
        request = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
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
