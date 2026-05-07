"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AI Service"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "ai_service"

    # JWT
    JWT_SECRET_KEY: str  # Required, no default for security
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = 3

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Internal API
    INTERNAL_API_KEY: str  # API key for Cloud Scheduler

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_JSON: str  # Service account credentials JSON
    GOOGLE_SERVICE_ACCOUNT_EMAIL: str  # Email to display to users

    # Sheet Crawler
    SHEET_SYNC_QUEUE_NAME: str = "sheet_sync_tasks"
    IMAGE_GENERATION_QUEUE_NAME: str = "image_generation_tasks"
    MEETING_NOTE_QUEUE_NAME: str = "meeting_note_tasks"
    STOCK_RESEARCH_QUEUE_NAME: str = "stock_research_tasks"
    IMAGE_GENERATION_MAX_CONCURRENCY: int = 4
    STOCK_RESEARCH_MAX_CONCURRENCY: int = 20
    LEAD_AGENT_MAX_DELEGATED_TASKS: int = 3
    LEAD_AGENT_MAX_PARALLEL_SUBAGENTS: int = 3
    LEAD_AGENT_SUBAGENT_TIMEOUT_SECONDS: float = 120.0
    LEAD_AGENT_DELEGATED_RESULT_MAX_CHARS: int = 2048
    STOCK_AGENT_MAX_DELEGATED_TASKS: int = 3
    STOCK_AGENT_MAX_PARALLEL_SUBAGENTS: int = 3
    STOCK_AGENT_SUBAGENT_TIMEOUT_SECONDS: float = 120.0
    STOCK_AGENT_DELEGATED_RESULT_MAX_CHARS: int = 2048

    # OpenAI
    OPENAI_API_KEY: str | None = None
    OPENAI_API_BASE: str | None = None  # Optional custom API base URL

    # LangSmith
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str | None = None

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_VERSION: str | None = None
    AZURE_OPENAI_LEGACY_CHAT_DEPLOYMENT: str | None = None

    # MiniMax
    MINIMAX_API_KEY: str
    MINIMAX_API_BASE: str = "https://api.minimax.io/v1"

    # ZAI
    ZAI_API_KEY: str | None = None
    ZAI_API_BASE: str = "https://api.z.ai/api/paas/v4"

    # Deepgram
    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "nova-3"
    DEEPGRAM_ENDPOINTING_MS: int = 400
    DEEPGRAM_UTTERANCE_END_MS: int = 1000
    DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS: int = 5

    # Interview STT
    INTERVIEW_STT_CHANNELS: int = 2
    INTERVIEW_STT_MULTICHANNEL: bool = True
    INTERVIEW_STT_ENDPOINTING_MS: int = 400
    INTERVIEW_STT_UTTERANCE_END_MS: int = 1000
    INTERVIEW_STT_KEEPALIVE_INTERVAL_SECONDS: int = 5
    INTERVIEW_TURN_CLOSE_GRACE_MS: int = 300

    # Meeting STT
    MEETING_STT_ENCODING: str = "linear16"
    MEETING_STT_SAMPLE_RATE: int = 16000
    MEETING_STT_CHANNELS: int = 1
    MEETING_STT_MULTICHANNEL: bool = False
    MEETING_STT_INTERIM_RESULTS: bool = True
    MEETING_STT_VAD_EVENTS: bool = True
    MEETING_STT_ENDPOINTING_MS: int = 400
    MEETING_STT_UTTERANCE_END_MS: int = 1000
    MEETING_STT_DIARIZE: bool = True
    MEETING_STT_SMART_FORMAT: bool = True
    MEETING_STT_PUNCTUATE: bool = True
    MEETING_STT_KEEPALIVE_INTERVAL_SECONDS: int = 5

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]  # Frontend origins

    # VNStock
    VNSTOCK_API_KEY: str


@lru_cache
def get_settings() -> Settings:
    """Dependency injection function for settings.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
