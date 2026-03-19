"""Socket event constants for WebSocket communication.

This module defines all socket event names used throughout the application
to avoid hardcoding event strings and ensure consistency.
"""


class SheetSyncEvents:
    """Socket events for sheet synchronization."""

    STARTED = "sheet:sync:started"
    COMPLETED = "sheet:sync:completed"
    FAILED = "sheet:sync:failed"
    PROGRESS = "sheet:sync:progress"


class ChatEvents:
    """Socket events for chat message streaming."""

    MESSAGE_STARTED = "chat:message:started"
    MESSAGE_TOKEN = "chat:message:token"
    MESSAGE_TOOL_START = "chat:message:tool_start"
    MESSAGE_TOOL_END = "chat:message:tool_end"
    MESSAGE_COMPLETED = "chat:message:completed"
    MESSAGE_FAILED = "chat:message:failed"


class TTSEvents:
    """Socket events for TTS streaming over the shared Socket.IO connection."""

    REQUEST = "tts:request"
    STARTED = "tts:started"
    AUDIO_CHUNK = "tts:audio:chunk"
    COMPLETED = "tts:completed"
    ERROR = "tts:error"


class STTEvents:
    """Socket events for live speech-to-text streaming over Socket.IO."""

    START = "stt:start"
    AUDIO = "stt:audio"
    FINALIZE = "stt:finalize"
    STOP = "stt:stop"
    STARTED = "stt:started"
    PARTIAL = "stt:partial"
    FINAL = "stt:final"
    UTTERANCE_CLOSED = "stt:utterance_closed"
    COMPLETED = "stt:completed"
    ERROR = "stt:error"


class InterviewEvents:
    """Socket events for interview-specific realtime flows."""

    ANSWER = "interview:answer"
    ANSWER_STARTED = "interview:answer:started"
    ANSWER_TOKEN = "interview:answer:token"
    ANSWER_COMPLETED = "interview:answer:completed"
    ANSWER_FAILED = "interview:answer:failed"


class MeetingRecordEvents:
    """Socket events for meeting recording realtime flows."""

    START = "meeting_record:start"
    AUDIO = "meeting_record:audio"
    STOP = "meeting_record:stop"
    STARTED = "meeting_record:started"
    TRANSCRIPT = "meeting_record:transcript"
    STOPPING = "meeting_record:stopping"
    COMPLETED = "meeting_record:completed"
    ERROR = "meeting_record:error"


class TextToImageGenerationEvents:
    """Socket events for text-to-image generation lifecycle."""

    CREATED = "image:generation:created"
    PROCESSING = "image:generation:processing"
    SUCCEEDED = "image:generation:succeeded"
    FAILED = "image:generation:failed"
    CANCELLED = "image:generation:cancelled"
