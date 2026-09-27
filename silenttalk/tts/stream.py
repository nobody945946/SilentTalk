"""Audio bytes that arrive over time, handed to FFmpeg as they come.

EdgeTTS delivers the first MP3 chunk well before the whole line (3050 Ti
laptop: ~0.45 s vs ~0.66 s for 16 characters), so playback can start on
the first chunk instead of on a finished file. The audio never touches the
disk (HANDOFF rule 1).
"""

from __future__ import annotations

import asyncio
import queue
from collections.abc import AsyncIterator, Callable


class AudioStream:
    """A blocking, file-like reader fed from the event loop.

    discord.py's FFmpeg source reads its `pipe=True` input with `read()` on a
    worker thread and stops at the first empty result, so `read()` blocks
    until data arrives and returns b"" once the producer is done or closed.
    """

    def __init__(self) -> None:
        self._chunks: queue.Queue[bytes | None] = queue.Queue()
        self._pending = b""
        self._ended = False
        self._task: asyncio.Task[None] | None = None
        self.error: BaseException | None = None

    def feed(self, data: bytes) -> None:
        if data:
            self._chunks.put(data)

    def finish(self, error: BaseException | None = None) -> None:
        if error is not None and self.error is None:
            self.error = error
        self._chunks.put(None)

    def read(self, size: int = -1) -> bytes:
        while not self._pending and not self._ended:
            chunk = self._chunks.get()
            if chunk is None:
                self._ended = True
            else:
                self._pending = chunk
        if size < 0 or size >= len(self._pending):
            data, self._pending = self._pending, b""
        else:
            data, self._pending = self._pending[:size], self._pending[size:]
        return data

    async def start(
        self,
        chunks: Callable[[], AsyncIterator[bytes]],
        *,
        first_chunk_timeout: float,
    ) -> None:
        """Pump `chunks()` into this stream in the background. Returns once the
        first chunk is in; errors before that are raised here, so a failed
        synthesis still fails the job instead of playing silence."""
        loop = asyncio.get_running_loop()
        first: asyncio.Future[None] = loop.create_future()

        async def pump() -> None:
            try:
                async for data in chunks():
                    self.feed(data)
                    if data and not first.done():
                        first.set_result(None)
                if not first.done():
                    first.set_exception(RuntimeError("EdgeTTS 產生空白音訊。"))
                self.finish()
            except asyncio.CancelledError:
                self.finish()
                raise
            except Exception as exc:  # network errors come in many types
                self.finish(exc)
                if not first.done():
                    first.set_exception(exc)

        self._task = loop.create_task(pump(), name="tts-stream")
        try:
            await asyncio.wait_for(asyncio.shield(first), timeout=first_chunk_timeout)
        except BaseException:
            first.cancel()
            self.close()
            raise

    def close(self) -> None:
        """Stop the producer and release a reader blocked in read()."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.finish()
