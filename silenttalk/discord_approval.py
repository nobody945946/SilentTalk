from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

import discord

_LOG = logging.getLogger(__name__)


class AgentApprovalView(discord.ui.View):
    """Only the configured owner can decide; every approval covers one call."""

    def __init__(
        self,
        owner_id: int,
        call_id: str,
        decide: Callable[[str, bool], Awaitable[bool]],
    ) -> None:
        super().__init__(timeout=290)
        self.owner_id, self.call_id, self.decide = owner_id, call_id, decide
        self.answered = False
        self.started = time.monotonic()
        for label, approved in (("准許", True), ("拒絕", False)):
            button = discord.ui.Button(
                label=label,
                style=(
                    discord.ButtonStyle.success
                    if approved
                    else discord.ButtonStyle.secondary
                ),
            )

            async def callback(
                interaction: discord.Interaction, choice: bool = approved
            ) -> None:
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message(
                        "只有主人能決定這件事。", ephemeral=True
                    )
                    return
                if self.answered:
                    await interaction.response.send_message(
                        "這個請求已經處理。", ephemeral=True
                    )
                    return
                self.answered = True
                await interaction.response.defer()
                try:
                    accepted = await self.decide(self.call_id, choice)
                    result = (
                        ("已准許這次操作。" if choice else "已拒絕這次操作。")
                        if accepted
                        else "這個請求已結束。"
                    )
                except Exception as exc:  # noqa: BLE001 - Discord callback must report delivery failures
                    _LOG.warning(
                        "agent_approval_response_failed error_type=%s",
                        type(exc).__name__,
                    )
                    result = "批准未送達，操作仍須等待或逾時拒絕。"
                for child in self.children:
                    child.disabled = True
                await interaction.edit_original_response(content=result, view=self)
                self.stop()
                _LOG.info(
                    "agent_approval_decided approved=%s roundtrip_ms=%d",
                    choice,
                    round((time.monotonic() - self.started) * 1000),
                )

            button.callback = callback
            self.add_item(button)

    async def on_timeout(self) -> None:
        if not self.answered:
            self.answered = True
            try:
                await self.decide(self.call_id, False)
            except Exception as exc:  # noqa: BLE001 - timed-out operations must remain denied
                _LOG.warning(
                    "agent_approval_timeout_failed error_type=%s", type(exc).__name__
                )
