"""STT service scaffolding."""

from __future__ import annotations

from app.services.stt.session_manager import STTSessionManager


class STTService:
    """Application service entry point for live speech-to-text flows."""

    def __init__(self, *, session_manager: STTSessionManager) -> None:
        self.session_manager = session_manager
