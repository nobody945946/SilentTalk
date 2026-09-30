from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are E4B, a capable local assistant. Answer in the user's language. "
    "Be direct, accurate, and preserve continuity with the supplied memory."
)
COMPACT_AT_TOKENS = 76_000
KEEP_RECENT_TOKENS = 20_000
SUMMARY_MAX_TOKENS = 2_048
MAX_REPLY_TOKENS = 4_096


@dataclass(slots=True)
class ChatSession:
    messages: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    compaction_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class NativeChat:
    """RAM-only E4B chat history with model-written semantic compaction."""

    def __init__(
        self,
        *,
        model_port: int,
        compact_at_tokens: int = COMPACT_AT_TOKENS,
        keep_recent_tokens: int = KEEP_RECENT_TOKENS,
    ) -> None:
        self.model_url = f"http://127.0.0.1:{model_port}"
        self.compact_at_tokens = compact_at_tokens
        self.keep_recent_tokens = keep_recent_tokens
        self._sessions: dict[str, ChatSession] = {}
        self._sessions_lock = threading.Lock()

    def reset(self, session_id: str) -> None:
        with self._sessions_lock:
            self._sessions.pop(session_id, None)

    def session(self, session_id: str) -> ChatSession:
        with self._sessions_lock:
            if session_id not in self._sessions and len(self._sessions) >= 32:
                self._sessions.pop(next(iter(self._sessions)))
            return self._sessions.setdefault(session_id, ChatSession())

    def stream_reply(
        self, session_id: str, user_text: str
    ) -> Iterator[tuple[str, dict[str, object]]]:
        session = self.session(session_id)
        with session.lock:
            session.messages.append({"role": "user", "content": user_text})
            try:
                compacted = self._compact_if_needed(session)
                if compacted:
                    yield (
                        "compacted",
                        {
                            "count": session.compaction_count,
                            "message": (
                                "已整理較早的對話記憶；重要資訊與近期內容已保留。"
                            ),
                        },
                    )
                answer = ""
                for piece in self._stream_completion(self._prompt_messages(session)):
                    answer += piece
                    yield "delta", {"text": piece}
                if not answer.strip():
                    raise RuntimeError("E4B returned an empty answer")
                session.messages.append({"role": "assistant", "content": answer})
                yield "done", {"compactions": session.compaction_count}
            except Exception:
                if session.messages and session.messages[-1].get("role") == "user":
                    session.messages.pop()
                raise

    def _compact_if_needed(self, session: ChatSession) -> bool:
        compacted = False
        for _ in range(3):
            if (
                self._input_tokens(self._prompt_messages(session))
                < self.compact_at_tokens
            ):
                return compacted
            split = self._recent_split(session.messages)
            if split <= 0:
                return compacted
            older = session.messages[:split]
            recent = session.messages[split:]
            session.summary = self._summarize(session.summary, older)
            session.messages = recent
            session.compaction_count += 1
            compacted = True
        if self._input_tokens(self._prompt_messages(session)) >= self.compact_at_tokens:
            raise RuntimeError("單次輸入太長，請縮短後再送出")
        return compacted

    def _recent_split(self, messages: list[dict[str, str]]) -> int:
        if len(messages) <= 4:
            return 0
        # Token/character ratios vary sharply for CJK, code, and emoji. Use the
        # model's tokenizer and a binary search instead of a character estimate.
        low = 0
        high = len(messages) - 4
        while low < high:
            middle = (low + high) // 2
            candidate = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *messages[middle:],
            ]
            if self._input_tokens(candidate) <= self.keep_recent_tokens:
                high = middle
            else:
                low = middle + 1
        return low

    def _prompt_messages(self, session: ChatSession) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if session.summary:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Memory distilled from earlier conversation. Treat it as context, "
                        "not as a new user request:\n" + session.summary
                    ),
                }
            )
        messages.extend(session.messages)
        return messages

    def _summarize(self, prior_summary: str, older: list[dict[str, str]]) -> str:
        transcript = "\n".join(f"{item['role']}: {item['content']}" for item in older)
        prompt = (
            "Compress the earlier conversation into durable memory for continuing it. "
            "Preserve user goals, preferences, facts, decisions, constraints, completed "
            "work, unresolved questions, and important reasoning. Remove repetition and "
            "small talk. Do not invent facts. Write compactly in the conversation's main "
            "language.\n\n"
            f"Previous memory:\n{prior_summary or '(none)'}\n\n"
            f"Older conversation:\n{transcript}"
        )
        response = self._complete(
            [
                {
                    "role": "system",
                    "content": "You are a precise semantic memory compressor.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.1,
        )
        if not response.strip():
            raise RuntimeError("E4B memory compaction returned an empty summary")
        return response.strip()

    def _input_tokens(self, messages: list[dict[str, str]]) -> int:
        value = self._post_json(
            "/v1/chat/completions/input_tokens",
            self._payload(messages, max_tokens=1, stream=False),
            timeout=30,
        )
        count = value.get("input_tokens")
        if not isinstance(count, int):
            raise TypeError("E4B tokenizer returned an invalid token count")
        return count

    def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        payload = self._payload(messages, max_tokens=max_tokens, stream=False)
        payload["temperature"] = temperature
        value = self._post_json("/v1/chat/completions", payload, timeout=180)
        try:
            content = value["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("E4B returned an invalid completion") from exc
        return content if isinstance(content, str) else ""

    def _stream_completion(self, messages: list[dict[str, str]]) -> Iterator[str]:
        request = urllib.request.Request(
            self.model_url + "/v1/chat/completions",
            data=json.dumps(
                self._payload(messages, max_tokens=MAX_REPLY_TOKENS, stream=True)
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        choice = json.loads(data)["choices"][0]
                        piece = (choice.get("delta") or {}).get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if piece:
                        yield piece
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError(f"E4B generation failed: {exc}") from exc

    def _post_json(
        self, path: str, payload: dict[str, object], *, timeout: float
    ) -> dict[str, object]:
        request = urllib.request.Request(
            self.model_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise RuntimeError(f"E4B model request failed: {exc}") from exc
        if not isinstance(value, dict):
            raise TypeError("E4B model returned invalid JSON")
        return value

    @staticmethod
    def _payload(
        messages: list[dict[str, str]], *, max_tokens: int, stream: bool
    ) -> dict[str, object]:
        return {
            "model": "local-e4b",
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": stream,
            "temperature": 0.7,
            "chat_template_kwargs": {"enable_thinking": False},
        }
