"""Deepgram live transcription client wrapper."""

from __future__ import annotations

from app.config.settings import get_settings


class DeepgramLiveClient:
    """Provider wrapper that centralizes Deepgram STT configuration.

    Task 1 only establishes the dependency boundary and shared configuration.
    The actual SDK websocket integration is implemented in later STT tasks.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        endpointing_ms: int | None = None,
        utterance_end_ms: int | None = None,
        keepalive_interval_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.model = model or settings.DEEPGRAM_MODEL
        self.endpointing_ms = (
            endpointing_ms
            if endpointing_ms is not None
            else settings.DEEPGRAM_ENDPOINTING_MS
        )
        self.utterance_end_ms = (
            utterance_end_ms
            if utterance_end_ms is not None
            else settings.DEEPGRAM_UTTERANCE_END_MS
        )
        self.keepalive_interval_seconds = (
            keepalive_interval_seconds
            if keepalive_interval_seconds is not None
            else settings.DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS
        )

    def get_runtime_config(self) -> dict[str, int | str]:
        """Return the provider runtime configuration for a new STT session."""
        return {
            "model": self.model,
            "endpointing_ms": self.endpointing_ms,
            "utterance_end_ms": self.utterance_end_ms,
            "keepalive_interval_seconds": self.keepalive_interval_seconds,
        }
