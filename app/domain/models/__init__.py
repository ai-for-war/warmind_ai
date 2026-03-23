"""Domain models for the application."""

from app.domain.models.audio_file import AudioFile
from app.domain.models.conversation import (
    Conversation,
    ConversationStatus,
)
from app.domain.models.image import Image, ImageSource
from app.domain.models.image_generation_job import (
    ImageGenerationJob,
    ImageGenerationJobStatus,
    ImageGenerationJobType,
    ImageGenerationProvider,
)
from app.domain.models.interview_conversation import (
    InterviewChannelMap,
    InterviewConversation,
    InterviewConversationStatus,
)
from app.domain.models.interview_utterance import (
    DURABLE_INTERVIEW_UTTERANCE_STATUSES,
    InterviewSpeakerRole,
    InterviewUtterance,
    InterviewUtteranceStatus,
)
from app.domain.models.meeting import (
    Meeting,
    MeetingArchiveScope,
    MeetingStatus,
)
from app.domain.models.meeting_note_chunk import (
    MeetingNoteActionItem,
    MeetingNoteChunk,
)
from app.domain.models.meeting_utterance import (
    MeetingUtterance,
    MeetingUtteranceMessage,
)
from app.domain.models.message import (
    Attachment,
    AttachmentType,
    Message,
    MessageMetadata,
    MessageRole,
    TokenUsage,
    ToolCall,
)
from app.domain.models.organization import (
    Organization,
    OrganizationMember,
    OrganizationRole,
)
from app.domain.models.sheet_connection import (
    SheetConnection,
    SheetRawData,
    SheetSyncState,
)
from app.domain.models.user import User, UserRole
from app.domain.models.voice import Voice, VoiceType

__all__ = [
    # Audio file models
    "AudioFile",
    # Conversation models
    "Conversation",
    "ConversationStatus",
    "InterviewChannelMap",
    "InterviewConversation",
    "InterviewConversationStatus",
    "InterviewSpeakerRole",
    "InterviewUtterance",
    "InterviewUtteranceStatus",
    "DURABLE_INTERVIEW_UTTERANCE_STATUSES",
    "Meeting",
    "MeetingArchiveScope",
    "MeetingStatus",
    "MeetingNoteActionItem",
    "MeetingNoteChunk",
    "MeetingUtterance",
    "MeetingUtteranceMessage",
    # Image models
    "Image",
    "ImageSource",
    "ImageGenerationJob",
    "ImageGenerationJobStatus",
    "ImageGenerationJobType",
    "ImageGenerationProvider",
    # Message models
    "Attachment",
    "AttachmentType",
    "Message",
    "MessageMetadata",
    "MessageRole",
    "TokenUsage",
    "ToolCall",
    # Organization models
    "Organization",
    "OrganizationMember",
    "OrganizationRole",
    # Sheet models
    "SheetConnection",
    "SheetRawData",
    "SheetSyncState",
    # User models
    "User",
    "UserRole",
    # Voice models
    "Voice",
    "VoiceType",
]
