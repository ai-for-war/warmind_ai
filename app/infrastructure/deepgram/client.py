"""Deepgram live transcription adapter using the official Python SDK."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.common.exceptions import STTProviderConnectionError
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class ProviderEventKind(str, Enum):
    """Normalized provider event kinds exposed to STT session code."""

    OPEN = "provider_open"
    TRANSCRIPT_PARTIAL = "provider_transcript_partial"
    TRANSCRIPT_FINAL_FRAGMENT = "provider_transcript_final_fragment"
    SPEECH_STARTED = "provider_speech_started"
    UTTERANCE_END = "provider_utterance_end"
    PROVIDER_FINALIZE = "provider_finalize"
    CLOSE = "provider_close"
    ERROR = "provider_error"


@dataclass(slots=True)
class ProviderTranscriptEvent:
    """Normalized transcript payload emitted by the provider adapter."""

    transcript: str
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    is_final: bool = False
    speech_final: bool = False
    from_finalize: bool = False


@dataclass(slots=True)
class ProviderEvent:
    """Provider-agnostic event model produced by the Deepgram adapter."""

    kind: ProviderEventKind
    transcript: ProviderTranscriptEvent | None = None
    last_word_end_ms: int | None = None
    error_message: str | None = None
    close_code: int | None = None
    metadata: dict[str, Any] | None = None


class DeepgramLiveClient:
    """Async Deepgram Listen V1 adapter.

    This module is the only code allowed to interact with the Deepgram SDK.
    It hides SDK message and control classes behind normalized dataclasses so
    the service/session layer does not couple to provider-specific types.
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
        self._client: Any | None = None
        self._connection_manager: Any | None = None
        self._connection: Any | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._events: asyncio.Queue[ProviderEvent] = asyncio.Queue()

    def get_runtime_config(self, *, language: str | None = None) -> dict[str, Any]:
        """Return verified Listen V1 connect options for the active STT runtime."""
        return {
            "model": self.model,
            "encoding": "linear16",
            # Deepgram's websocket query parser expects string query values.
            "sample_rate": "16000",
            "channels": "1",
            "interim_results": "true",
            "vad_events": "true",
            "endpointing": str(self.endpointing_ms),
            "utterance_end_ms": str(self.utterance_end_ms),
            "language": language or "en",
        }

    async def open(self, *, language: str | None = None) -> None:
        """Open an async Listen V1 websocket and register SDK event handlers."""
        if self._connection is not None:
            raise STTProviderConnectionError("Deepgram connection is already open")

        try:
            from deepgram import AsyncDeepgramClient
            from deepgram.core.events import EventType
        except ImportError as exc:
            raise STTProviderConnectionError("deepgram-sdk is not installed") from exc

        listen_options = self.get_runtime_config(language=language)

        try:
            self._event_loop = asyncio.get_running_loop()
            self._client = AsyncDeepgramClient(api_key=self.api_key)
            self._connection_manager = self._client.listen.v1.connect(**listen_options)
            self._connection = await self._connection_manager.__aenter__()

            self._connection.on(EventType.OPEN, self._on_open)
            self._connection.on(EventType.MESSAGE, self._on_message)
            self._connection.on(EventType.CLOSE, self._on_close)
            self._connection.on(EventType.ERROR, self._on_error)

            self._listener_task = asyncio.create_task(self._connection.start_listening())
            logger.info(
                "Deepgram live connection started provider %s model %s language %s",
                "deepgram",
                self.model,
                listen_options["language"],
            )
        except Exception as exc:
            await self._cleanup_connection_context()
            logger.error(
                "Deepgram live connection failed to start: %s",
                self._sanitize_exception_message(exc),
            )
            raise STTProviderConnectionError(
                "Failed to open Deepgram live connection"
            ) from exc

    async def send_audio(self, chunk: bytes) -> bool:
        """Stream PCM audio bytes to Deepgram via the SDK media path."""
        connection = self._require_connection()

        try:
            await connection.send_media(chunk)
            return True
        except Exception as exc:
            raise STTProviderConnectionError(
                "Failed to send audio to Deepgram"
            ) from exc

    async def send_keepalive(self) -> bool:
        """Send a provider keepalive control message."""
        return await self._send_control_message("KeepAlive")

    async def finalize(self) -> bool:
        """Send a provider finalize control message."""
        return await self._send_control_message("Finalize")

    async def close(self) -> bool:
        """Close the provider stream cleanly."""
        connection = self._connection
        if connection is None:
            return True

        success = True
        try:
            await connection.send_close_stream()
            logger.info("Deepgram live connection finished")
        except Exception as exc:
            success = False
            logger.warning("Deepgram finish failed: %s", exc)
        finally:
            await self._cleanup_connection_context()

        return success

    async def next_event(self) -> ProviderEvent:
        """Wait for the next normalized provider event."""
        return await self._events.get()

    def drain_pending_events(self) -> list[ProviderEvent]:
        """Drain any currently queued provider events without waiting."""
        events: list[ProviderEvent] = []
        while not self._events.empty():
            events.append(self._events.get_nowait())
        return events

    async def _send_control_message(self, control_type: str) -> bool:
        connection = self._require_connection()

        try:
            if control_type == "KeepAlive":
                await connection.send_keep_alive()
                return True
            if control_type == "Finalize":
                await connection.send_finalize()
                return True
            raise ValueError(f"Unsupported Deepgram control message: {control_type}")
        except Exception as exc:
            raise STTProviderConnectionError(
                f"Failed to send Deepgram control message: {control_type}"
            ) from exc

    def _require_connection(self) -> Any:
        if self._connection is None:
            raise STTProviderConnectionError("Deepgram connection is not open")
        return self._connection

    def _on_open(self, _: Any) -> None:
        logger.info("Deepgram provider connection opened")
        self._publish_event(ProviderEvent(kind=ProviderEventKind.OPEN))

    def _on_close(self, payload: Any) -> None:
        close_code = self._safe_int(getattr(payload, "code", None))
        logger.info(
            "Deepgram provider connection closed", extra={"close_code": close_code}
        )
        self._publish_event(
            ProviderEvent(
                kind=ProviderEventKind.CLOSE,
                close_code=close_code,
            )
        )

    def _on_error(self, payload: Any) -> None:
        error_message = self._stringify_error(payload)
        logger.error("Deepgram provider error: %s", error_message)
        self._publish_event(
            ProviderEvent(
                kind=ProviderEventKind.ERROR,
                error_message=error_message,
            )
        )

    def _on_message(self, message: Any) -> None:
        provider_event = self._normalize_message(message)
        if provider_event is None:
            return

        if (
            provider_event.kind
            in {
                ProviderEventKind.TRANSCRIPT_PARTIAL,
                ProviderEventKind.TRANSCRIPT_FINAL_FRAGMENT,
            }
            and provider_event.transcript is not None
        ):
            logger.debug(
                "Deepgram transcript event",
                extra={
                    "is_final": provider_event.transcript.is_final,
                    "speech_final": provider_event.transcript.speech_final,
                    "from_finalize": provider_event.transcript.from_finalize,
                    "transcript_chars": len(provider_event.transcript.transcript),
                },
            )
        elif provider_event.kind == ProviderEventKind.SPEECH_STARTED:
            logger.debug("Deepgram speech started")
        elif provider_event.kind == ProviderEventKind.UTTERANCE_END:
            logger.debug(
                "Deepgram utterance end",
                extra={"last_word_end_ms": provider_event.last_word_end_ms},
            )
        elif provider_event.kind == ProviderEventKind.PROVIDER_FINALIZE:
            logger.debug("Deepgram finalize signal")

        self._publish_event(provider_event)

    def _normalize_message(self, message: Any) -> ProviderEvent | None:
        message_type = str(getattr(message, "type", "") or "").lower()

        if "utteranceend" in message_type:
            return ProviderEvent(
                kind=ProviderEventKind.UTTERANCE_END,
                last_word_end_ms=self._seconds_to_ms(
                    getattr(message, "last_word_end", None)
                ),
            )

        if "speechstarted" in message_type:
            return ProviderEvent(kind=ProviderEventKind.SPEECH_STARTED)

        if "finalize" in message_type:
            return ProviderEvent(kind=ProviderEventKind.PROVIDER_FINALIZE)

        transcript = self._extract_transcript_event(message)
        if transcript is not None:
            kind = (
                ProviderEventKind.TRANSCRIPT_FINAL_FRAGMENT
                if transcript.is_final
                else ProviderEventKind.TRANSCRIPT_PARTIAL
            )
            return ProviderEvent(kind=kind, transcript=transcript)

        if "error" in message_type:
            return ProviderEvent(
                kind=ProviderEventKind.ERROR,
                error_message=self._stringify_error(message),
            )

        return None

    def _extract_transcript_event(self, message: Any) -> ProviderTranscriptEvent | None:
        channel = getattr(message, "channel", None)
        alternatives = getattr(channel, "alternatives", None)
        first_alternative = (
            alternatives[0] if isinstance(alternatives, list) and alternatives else None
        )
        if first_alternative is None:
            return None

        transcript = str(getattr(first_alternative, "transcript", "") or "").strip()
        if not transcript:
            return None

        words = getattr(first_alternative, "words", None)
        start_ms, end_ms = self._extract_word_window(words)

        return ProviderTranscriptEvent(
            transcript=transcript,
            confidence=self._safe_float(getattr(first_alternative, "confidence", None)),
            start_ms=start_ms,
            end_ms=end_ms,
            is_final=bool(getattr(message, "is_final", False)),
            speech_final=bool(getattr(message, "speech_final", False)),
            from_finalize=bool(getattr(message, "from_finalize", False)),
        )

    def _extract_word_window(self, words: Any) -> tuple[int | None, int | None]:
        if not isinstance(words, list) or not words:
            return None, None

        first = words[0]
        last = words[-1]
        return (
            self._seconds_to_ms(getattr(first, "start", None)),
            self._seconds_to_ms(getattr(last, "end", None)),
        )

    def _publish_event(self, event: ProviderEvent) -> None:
        if self._event_loop is None:
            return
        self._event_loop.call_soon_threadsafe(self._events.put_nowait, event)

    async def _cleanup_connection_context(self) -> None:
        connection_manager = self._connection_manager
        listener_task = self._listener_task
        self._connection = None
        self._connection_manager = None
        self._client = None
        self._listener_task = None

        if listener_task is not None and not listener_task.done():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Deepgram listener task cleanup raised", exc_info=True)

        if connection_manager is not None:
            try:
                await connection_manager.__aexit__(None, None, None)
            except Exception:
                logger.debug(
                    "Deepgram connection context cleanup raised", exc_info=True
                )

    @staticmethod
    def _seconds_to_ms(value: Any) -> int | None:
        numeric = DeepgramLiveClient._safe_float(value)
        if numeric is None:
            return None
        return int(numeric * 1000)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _stringify_error(payload: Any) -> str:
        if payload is None:
            return "Unknown Deepgram error"
        message = getattr(payload, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        return str(payload)

    @staticmethod
    def _sanitize_exception_message(exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        if status_code is not None or body is not None:
            details: list[str] = []
            if status_code is not None:
                details.append(f"status_code={status_code}")
            if body:
                details.append(f"body={body}")
            if details:
                return "Deepgram API error (" + ", ".join(details) + ")"

        message = str(exc)
        return re.sub(
            r"(Authorization':\s*')([^']+)(')",
            r"\1[REDACTED]\3",
            message,
        )
