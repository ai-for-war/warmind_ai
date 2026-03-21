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
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1close_stream import ListenV1CloseStream
from deepgram.listen.v1.types.listen_v1finalize import ListenV1Finalize
from deepgram.listen.v1.types.listen_v1keep_alive import ListenV1KeepAlive

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
    channel_index: int | None = None
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    is_final: bool = False
    speech_final: bool = False
    from_finalize: bool = False
    words: tuple["ProviderTranscriptWord", ...] = ()


@dataclass(slots=True)
class ProviderTranscriptWord:
    """Normalized word-level transcript token for additive diarization support."""

    text: str
    speaker_index: int | None = None
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(slots=True)
class ProviderEvent:
    """Provider-agnostic event model produced by the Deepgram adapter."""

    kind: ProviderEventKind
    channel_index: int | None = None
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
        encoding: str | None = None,
        sample_rate: int | None = None,
        channels: int | None = None,
        multichannel: bool | None = None,
        interim_results: bool | None = None,
        vad_events: bool | None = None,
        endpointing_ms: int | None = None,
        utterance_end_ms: int | None = None,
        diarize: bool | None = None,
        smart_format: bool | None = None,
        punctuate: bool | None = None,
        keepalive_interval_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.model = model or settings.DEEPGRAM_MODEL
        self.encoding = encoding or "linear16"
        self.sample_rate = sample_rate or 16000
        self.channels = (
            channels if channels is not None else settings.INTERVIEW_STT_CHANNELS
        )
        self.multichannel = (
            multichannel
            if multichannel is not None
            else settings.INTERVIEW_STT_MULTICHANNEL
        )
        self.interim_results = (
            interim_results if interim_results is not None else True
        )
        self.vad_events = vad_events if vad_events is not None else True
        self.endpointing_ms = (
            endpointing_ms
            if endpointing_ms is not None
            else settings.INTERVIEW_STT_ENDPOINTING_MS
        )
        self.utterance_end_ms = (
            utterance_end_ms
            if utterance_end_ms is not None
            else settings.INTERVIEW_STT_UTTERANCE_END_MS
        )
        self.diarize = diarize
        self.smart_format = smart_format
        self.punctuate = punctuate
        self.keepalive_interval_seconds = (
            keepalive_interval_seconds
            if keepalive_interval_seconds is not None
            else settings.INTERVIEW_STT_KEEPALIVE_INTERVAL_SECONDS
        )
        self._client: Any | None = None
        self._connection_manager: Any | None = None
        self._connection: Any | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._events: asyncio.Queue[ProviderEvent] = asyncio.Queue()
        self._connect_options: dict[str, Any] | None = None
        self._last_request_metadata: dict[str, Any] | None = None

    @classmethod
    def for_meeting(cls) -> "DeepgramLiveClient":
        """Build a Deepgram client pinned to the meeting transcription contract."""
        settings = get_settings()
        return cls(
            encoding=settings.MEETING_STT_ENCODING,
            sample_rate=settings.MEETING_STT_SAMPLE_RATE,
            channels=settings.MEETING_STT_CHANNELS,
            multichannel=settings.MEETING_STT_MULTICHANNEL,
            interim_results=settings.MEETING_STT_INTERIM_RESULTS,
            vad_events=settings.MEETING_STT_VAD_EVENTS,
            endpointing_ms=settings.MEETING_STT_ENDPOINTING_MS,
            utterance_end_ms=settings.MEETING_STT_UTTERANCE_END_MS,
            diarize=settings.MEETING_STT_DIARIZE,
            smart_format=settings.MEETING_STT_SMART_FORMAT,
            punctuate=settings.MEETING_STT_PUNCTUATE,
            keepalive_interval_seconds=settings.MEETING_STT_KEEPALIVE_INTERVAL_SECONDS,
        )

    def get_runtime_config(self, *, language: str | None = None) -> dict[str, Any]:
        """Return verified Listen V1 connect options for the active STT runtime."""
        runtime_config = {
            "model": self.model,
            "encoding": self.encoding,
            # Deepgram's websocket query parser expects string query values.
            "sample_rate": str(self.sample_rate),
            "channels": str(self.channels),
            "multichannel": str(self.multichannel).lower(),
            "interim_results": str(self.interim_results).lower(),
            "vad_events": str(self.vad_events).lower(),
            "endpointing": str(self.endpointing_ms),
            "utterance_end_ms": str(self.utterance_end_ms),
            "language": language or "en",
        }
        for key, value in {
            "diarize": self.diarize,
            "smart_format": self.smart_format,
            "punctuate": self.punctuate,
        }.items():
            if value is not None:
                runtime_config[key] = str(value).lower()
        return runtime_config

    async def open(self, *, language: str | None = None) -> None:
        """Open an async Listen V1 websocket and register SDK event handlers."""
        if self._connection is not None:
            raise STTProviderConnectionError("Deepgram connection is already open")

        listen_options = self.get_runtime_config(language=language)
        self._connect_options = dict(listen_options)

        try:
            self._event_loop = asyncio.get_running_loop()
            self._client = AsyncDeepgramClient(api_key=self.api_key)
            self._connection_manager = self._client.listen.v1.connect(**listen_options)
            self._connection = await self._connection_manager.__aenter__()

            self._connection.on(EventType.OPEN, self._on_open)
            self._connection.on(EventType.MESSAGE, self._on_message)
            self._connection.on(EventType.CLOSE, self._on_close)
            self._connection.on(EventType.ERROR, self._on_error)

            self._listener_task = asyncio.create_task(
                self._connection.start_listening()
            )
            logger.info(
                "Deepgram live connection started",
                extra={
                    "provider": "deepgram",
                    "model": self.model,
                    "language": listen_options["language"],
                    "channels": self.channels,
                    "multichannel": self.multichannel,
                    "endpointing": listen_options["endpointing"],
                    "utterance_end_ms": listen_options["utterance_end_ms"],
                },
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
        """Close the provider stream cleanly via CloseStream.

        Finalize and CloseStream remain distinct behaviors. Callers can use
        ``finalize()`` to flush pending transcript results while keeping the
        websocket alive long enough to consume them, then call ``close()`` only
        when the session itself should terminate.
        """
        connection = self._connection
        if connection is None:
            return True

        success = True
        try:
            await connection.send_close_stream(
                ListenV1CloseStream(type="CloseStream")
            )
            logger.info(
                "Deepgram close stream requested",
                extra=self._provider_log_context(),
            )
            await self._await_listener_shutdown(timeout_seconds=1.0)
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
                await connection.send_keep_alive(ListenV1KeepAlive(type="KeepAlive"))
                logger.debug(
                    "Deepgram keepalive requested",
                    extra=self._provider_log_context(),
                )
                return True
            if control_type == "Finalize":
                await connection.send_finalize(ListenV1Finalize(type="Finalize"))
                logger.info(
                    "Deepgram finalize requested",
                    extra=self._provider_log_context(),
                )
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
        logger.info("Deepgram provider connection opened", extra=self._provider_log_context())
        self._publish_event(
            ProviderEvent(
                kind=ProviderEventKind.OPEN,
                metadata=dict(self._connect_options or {}),
            )
        )

    def _on_close(self, payload: Any) -> None:
        close_code = self._safe_int(getattr(payload, "code", None))
        logger.info(
            "Deepgram provider connection closed",
            extra={
                **self._provider_log_context(),
                "close_code": close_code,
            },
        )
        self._publish_event(
            ProviderEvent(
                kind=ProviderEventKind.CLOSE,
                close_code=close_code,
            )
        )

    def _on_error(self, payload: Any) -> None:
        error_message = self._stringify_error(payload)
        logger.error(
            "Deepgram provider error: %s",
            error_message,
            extra=self._provider_log_context(),
        )
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

        self._remember_request_metadata(provider_event.metadata)
        logger.debug(
            "Deepgram provider event",
            extra=self._build_provider_event_log_extra(provider_event),
        )

        self._publish_event(provider_event)

    def _normalize_message(self, message: Any) -> ProviderEvent | None:
        message_type = str(getattr(message, "type", "") or "").lower()
        channel_indices = self._extract_channel_indices(
            getattr(message, "channel_index", None)
        ) or self._extract_channel_indices(getattr(message, "channel", None))
        channel_index = channel_indices[0] if channel_indices else None
        metadata = self._extract_provider_metadata(
            message,
            channel_indices=channel_indices,
        )

        if "utteranceend" in message_type:
            return ProviderEvent(
                kind=ProviderEventKind.UTTERANCE_END,
                channel_index=channel_index,
                last_word_end_ms=self._seconds_to_ms(
                    getattr(message, "last_word_end", None)
                ),
                metadata=metadata,
            )

        if "speechstarted" in message_type:
            return ProviderEvent(
                kind=ProviderEventKind.SPEECH_STARTED,
                channel_index=channel_index,
                metadata=metadata,
            )

        if "finalize" in message_type:
            return ProviderEvent(
                kind=ProviderEventKind.PROVIDER_FINALIZE,
                channel_index=channel_index,
                metadata=metadata,
            )

        transcript = self._extract_transcript_event(
            message,
            channel_index=channel_index,
        )
        if transcript is not None:
            kind = (
                ProviderEventKind.TRANSCRIPT_FINAL_FRAGMENT
                if transcript.is_final
                else ProviderEventKind.TRANSCRIPT_PARTIAL
            )
            return ProviderEvent(
                kind=kind,
                channel_index=transcript.channel_index,
                transcript=transcript,
                metadata=metadata,
            )

        if "error" in message_type:
            return ProviderEvent(
                kind=ProviderEventKind.ERROR,
                error_message=self._stringify_error(message),
                metadata=metadata,
            )

        return None

    def _extract_transcript_event(
        self,
        message: Any,
        *,
        channel_index: int | None,
    ) -> ProviderTranscriptEvent | None:
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
        normalized_words = self._extract_transcript_words(words)

        return ProviderTranscriptEvent(
            transcript=transcript,
            channel_index=channel_index,
            confidence=self._safe_float(getattr(first_alternative, "confidence", None)),
            start_ms=start_ms,
            end_ms=end_ms,
            is_final=bool(getattr(message, "is_final", False)),
            speech_final=bool(getattr(message, "speech_final", False)),
            from_finalize=bool(getattr(message, "from_finalize", False)),
            words=normalized_words,
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

    def _extract_transcript_words(
        self,
        words: Any,
    ) -> tuple[ProviderTranscriptWord, ...]:
        if not isinstance(words, list) or not words:
            return ()

        normalized_words: list[ProviderTranscriptWord] = []
        for raw_word in words:
            word_payload = self._coerce_object_to_dict(raw_word)
            text = str(
                word_payload.get("punctuated_word")
                or word_payload.get("word")
                or ""
            ).strip()
            if not text:
                continue

            normalized_words.append(
                ProviderTranscriptWord(
                    text=text,
                    speaker_index=self._safe_int(word_payload.get("speaker")),
                    confidence=self._safe_float(word_payload.get("confidence")),
                    start_ms=self._seconds_to_ms(word_payload.get("start")),
                    end_ms=self._seconds_to_ms(word_payload.get("end")),
                )
            )

        return tuple(normalized_words)

    def _publish_event(self, event: ProviderEvent) -> None:
        if self._event_loop is None:
            return
        self._event_loop.call_soon_threadsafe(self._events.put_nowait, event)

    async def _await_listener_shutdown(self, *, timeout_seconds: float) -> None:
        listener_task = self._listener_task
        if listener_task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(listener_task), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.debug(
                "Timed out waiting for Deepgram listener shutdown",
                extra=self._provider_log_context(),
            )
        except Exception:
            logger.debug(
                "Deepgram listener shutdown raised",
                extra=self._provider_log_context(),
                exc_info=True,
            )

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
    def _coerce_object_to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        if hasattr(value, "to_dict"):
            try:
                mapped = value.to_dict()
            except Exception:
                mapped = None
            if isinstance(mapped, dict):
                return mapped

        if hasattr(value, "__dict__"):
            return dict(vars(value))

        return {
            key: getattr(value, key)
            for key in (
                "word",
                "punctuated_word",
                "speaker",
                "confidence",
                "start",
                "end",
            )
            if hasattr(value, key)
        }

    @classmethod
    def _extract_channel_indices(cls, value: Any) -> tuple[int, ...] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            normalized = tuple(
                item for item in (cls._safe_int(raw) for raw in value) if item is not None
            )
            return normalized or None
        normalized = cls._safe_int(value)
        if normalized is None:
            return None
        return (normalized,)

    @classmethod
    def _extract_provider_metadata(
        cls,
        message: Any,
        *,
        channel_indices: tuple[int, ...] | None = None,
    ) -> dict[str, Any] | None:
        metadata_payload: dict[str, Any] = {}
        metadata = getattr(message, "metadata", None)
        if metadata is not None:
            request_id = getattr(metadata, "request_id", None)
            if request_id:
                metadata_payload["request_id"] = request_id

            model_uuid = getattr(metadata, "model_uuid", None)
            if model_uuid:
                metadata_payload["model_uuid"] = model_uuid

            model_info = getattr(metadata, "model_info", None)
            if model_info is not None:
                model_name = getattr(model_info, "name", None)
                model_version = getattr(model_info, "version", None)
                model_arch = getattr(model_info, "arch", None)
                if model_name:
                    metadata_payload["model_name"] = model_name
                if model_version:
                    metadata_payload["model_version"] = model_version
                if model_arch:
                    metadata_payload["model_arch"] = model_arch

        if channel_indices:
            metadata_payload["channel_indices"] = list(channel_indices)

        return metadata_payload or None

    def _remember_request_metadata(self, metadata: dict[str, Any] | None) -> None:
        if not metadata:
            return
        remembered = dict(self._last_request_metadata or {})
        for key in ("request_id", "model_uuid", "model_name", "model_version", "model_arch"):
            value = metadata.get(key)
            if value is not None:
                remembered[key] = value
        if remembered:
            self._last_request_metadata = remembered

    def _provider_log_context(self) -> dict[str, Any]:
        context: dict[str, Any] = {"provider": "deepgram"}
        if self._last_request_metadata:
            context.update(self._last_request_metadata)
        return context

    def _build_provider_event_log_extra(
        self,
        event: ProviderEvent,
    ) -> dict[str, Any]:
        extra = self._provider_log_context()
        extra["event_kind"] = event.kind.value
        if event.metadata:
            extra.update(event.metadata)
        if event.channel_index is not None:
            extra["channel_index"] = event.channel_index
        if event.last_word_end_ms is not None:
            extra["last_word_end_ms"] = event.last_word_end_ms
        if event.close_code is not None:
            extra["close_code"] = event.close_code
        if event.transcript is not None:
            extra["is_final"] = event.transcript.is_final
            extra["speech_final"] = event.transcript.speech_final
            extra["from_finalize"] = event.transcript.from_finalize
            extra["transcript_chars"] = len(event.transcript.transcript)
        return extra

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
