"""STT session manager scaffolding."""

from __future__ import annotations

from collections.abc import Callable

from app.infrastructure.deepgram.client import DeepgramLiveClient


class STTSessionManager:
    """Owns STT session dependencies and per-socket session lifecycle state."""

    def __init__(
        self,
        *,
        deepgram_client_factory: Callable[[], DeepgramLiveClient],
    ) -> None:
        self._deepgram_client_factory = deepgram_client_factory

    def create_provider_client(self) -> DeepgramLiveClient:
        """Create a provider wrapper for a new STT session."""
        return self._deepgram_client_factory()
