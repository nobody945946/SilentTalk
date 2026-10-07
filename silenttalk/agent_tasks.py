"""RAM-only EdgeAgent task transport; EdgeAgent owns all permission decisions."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

import aiohttp

from silenttalk.agent_lease import CONTROL_PORT, AgentLeaseError

TaskEvent = Callable[[str, dict[str, object]], Awaitable[None]]


def client_failure(exc: BaseException) -> str:
    """A stable code for a task that failed on the way to or from EdgeAgent
    (EdgeAgent's own failures arrive with their code in the error event)."""
    if isinstance(exc, TimeoutError):
        return "read_timeout"
    if isinstance(exc, aiohttp.ClientResponseError):
        return f"http_{exc.status}"
    if isinstance(exc, (aiohttp.ClientError, OSError)):
        return "connection"
    if isinstance(exc, AgentLeaseError):
        return "stream_ended"
    return "invalid_event"


class AgentTaskClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or f"http://127.0.0.1:{CONTROL_PORT}"
        self.session_id: str | None = None

    async def workspace(self) -> str:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as client,
            client.get(self.base_url + "/config") as response,
        ):
            response.raise_for_status()
            profile = (await response.json())["permissions"]["discord"]
        if not profile.get("enabled"):
            raise AgentLeaseError("請主人先在 EdgeAgent 的權限頁開啟 Discord Agent。")
        roots = profile.get("workspaces", [])
        if not roots:
            raise AgentLeaseError(
                "請主人先在 EdgeAgent 的 Discord 權限設定工作資料夾。"
            )
        return str(roots[0])

    async def run(
        self, text: str, workspace: str, on_event: TaskEvent, *,
        scope: str = "read", conversation: int | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> None:
        """One task. `scope` (EdgeAgent's task scope): "read" refuses every
        change, "change" asks the owner for each, "public" leaves the web
        alone. `conversation`: the place it was asked in (the voice room, a
        text channel or a thread); its tasks share one EdgeAgent session, so
        the Agent knows what it did there before (in EdgeAgent's RAM).
        Without it the task is a session of its own. `attachments`: files
        posted with the request, {"name", "data" (base64)}, which EdgeAgent
        decodes in memory (images go to the model, documents as text)."""
        if self.session_id is not None:
            raise AgentLeaseError("Agent 工作正在進行。")
        session_id = self.session_id = (
            f"discord-{conversation}" if conversation is not None else str(uuid4())
        )
        terminal = False
        try:
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=330)
            async with (
                aiohttp.ClientSession(timeout=timeout) as client,
                client.post(
                    self.base_url + "/chat",
                    json={
                        "session_id": session_id,
                        "text": text,
                        "client": "discord",
                        "agent": True,
                        "working_dir": workspace,
                        "scope": scope,
                        "attachments": attachments or [],
                    },
                ) as response,
            ):
                response.raise_for_status()
                event, lines = "message", []
                async for raw in response.content:
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if lines:
                            payload = json.loads("\n".join(lines))
                            if not isinstance(payload, dict):
                                raise ValueError("invalid task event")
                            await on_event(event, payload)
                            if event in {"done", "error", "cancelled"}:
                                terminal = True
                                return
                        event, lines = "message", []
                    elif line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        lines.append(line[5:].lstrip(" "))
                raise AgentLeaseError("Agent 連線結束，沒有完成事件。")
        except asyncio.CancelledError:
            raise
        except (aiohttp.ClientError, OSError, ValueError, AgentLeaseError) as exc:
            await on_event("error", {"message": str(exc), "reason": client_failure(exc)})
        finally:
            if not terminal:
                try:
                    await self.cancel()
                except (aiohttp.ClientError, OSError, TimeoutError):
                    pass
            self.session_id = None

    async def _control(
        self, path: str, payload: dict[str, object]
    ) -> dict[str, object]:
        if self.session_id is None:
            return {"accepted": False}
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as client,
            client.post(
                self.base_url + path,
                json={
                    "session_id": self.session_id,
                    **payload,
                },
            ) as response,
        ):
            response.raise_for_status()
            return await response.json()

    async def approve(self, call_id: str, approved: bool) -> bool:
        result = await self._control(
            "/chat/approve",
            {
                "call_id": call_id,
                "approved": approved,
                "scope": "once",
            },
        )
        return result.get("accepted") is True

    async def cancel(self) -> None:
        await self._control("/chat/cancel", {})
