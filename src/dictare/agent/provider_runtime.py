"""Dedicated event loop for provider I/O and synchronous engine delivery."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

from dictare.agent.codex_sessions import CodexSessions
from dictare.agent.provider_routing import ProviderRouter, ProviderSession

T = TypeVar("T")


class ProviderRuntime:
    """Own a loop separate from both the engine and the HTTP server."""

    def __init__(self, codex: CodexSessions | None = None) -> None:
        self.codex = codex or CodexSessions()
        self.router = ProviderRouter([self.codex])
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="provider-runtime", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        self._loop.close()

    def submit(self, coroutine: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        if not self._thread.is_alive():
            coroutine.close()
            raise RuntimeError("Provider runtime has stopped")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def deliver(self, target: ProviderSession, prompt: str) -> bool:
        """Block an engine thread until acceptance, or report uncertain failure."""
        future = self.submit(self.router.send_to(target, prompt))
        try:
            future.result(timeout=35)
            return True
        except Exception:
            future.cancel()
            return False

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        try:
            self.submit(self.codex.close()).result(timeout=20)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
