"""TTS service for stream/sync synthesis and generated audio management."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.common.exceptions import (
    AudioFileNotFoundError,
    AppException,
    PermissionDeniedError,
    VoiceNotFoundError,
)
from app.common.utils import is_org_admin, is_super_admin
from app.domain.models.audio_file import AudioFile
from app.domain.models.organization import OrganizationRole
from app.domain.models.user import UserRole
from app.domain.models.voice import Voice
from app.domain.schemas.tts import (
    AudioDetailResponse,
    AudioFileRecord,
    AudioListResponse,
    GenerateAudioResponse,
)
from app.infrastructure.cloudinary.client import CloudinaryClient
from app.infrastructure.minimax.client import MiniMaxClient
from app.repo.audio_file_repo import AudioFileRepository
from app.repo.voice_repo import VoiceRepository


class TTSService:
    """Service for TTS generation, streaming, and audio file lifecycle."""

    def __init__(
        self,
        audio_file_repo: AudioFileRepository,
        voice_repo: VoiceRepository,
        cloudinary_client: CloudinaryClient,
        minimax_client: MiniMaxClient,
    ):
        """Initialize TTSService with repositories and provider clients."""
        self.audio_file_repo = audio_file_repo
        self.voice_repo = voice_repo
        self.cloudinary_client = cloudinary_client
        self.minimax_client = minimax_client

    async def synthesize_stream(
        self,
        *,
        text: str,
        voice_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
        speed: float | None = None,
        volume: float | None = None,
        pitch: int | None = None,
        emotion: str | None = None,
        on_completed: Callable[[GenerateAudioResponse], Awaitable[None]] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesized audio chunks and persist completed audio metadata."""
        self._validate_text(text)
        await self._validate_voice_access(
            voice_id=voice_id,
            user_id=user_id,
            user_role=user_role,
            org_id=org_id,
            org_role=org_role,
        )

        chunks: list[bytes] = []
        async for chunk in self.minimax_client.synthesize_stream(
            text=text,
            voice_id=voice_id,
            speed=speed if speed is not None else 1.0,
            vol=volume if volume is not None else 1.0,
            pitch=pitch if pitch is not None else 0,
            emotion=emotion,
        ):
            if not chunk:
                continue
            chunks.append(chunk)
            yield chunk

        if not chunks:
            raise AppException("Synthesis failed")

        audio_bytes = b"".join(chunks)
        response = await self._persist_audio(
            audio_bytes=audio_bytes,
            text=text,
            voice_id=voice_id,
            org_id=org_id,
            user_id=user_id,
        )
        if on_completed is not None:
            await on_completed(response)

    async def generate_audio(
        self,
        *,
        text: str,
        voice_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
        speed: float | None = None,
        volume: float | None = None,
        pitch: int | None = None,
        emotion: str | None = None,
    ) -> GenerateAudioResponse:
        """Generate TTS audio synchronously, persist it, and return metadata + signed URL."""
        self._validate_text(text)
        await self._validate_voice_access(
            voice_id=voice_id,
            user_id=user_id,
            user_role=user_role,
            org_id=org_id,
            org_role=org_role,
        )

        result = await self.minimax_client.synthesize_sync(
            text=text,
            voice_id=voice_id,
            speed=speed if speed is not None else 1.0,
            vol=volume if volume is not None else 1.0,
            pitch=pitch if pitch is not None else 0,
            emotion=emotion,
        )
        return await self._persist_audio(
            audio_bytes=result["audio_bytes"],
            text=text,
            voice_id=voice_id,
            org_id=org_id,
            user_id=user_id,
            duration_ms=result.get("duration_ms"),
            size_bytes=result.get("size_bytes"),
        )

    async def get_audio(
        self,
        *,
        audio_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> AudioDetailResponse:
        """Get audio metadata with signed URL and 3-tier access control."""
        audio = await self.audio_file_repo.find_by_id_and_org(audio_id=audio_id, org_id=org_id)
        if audio is None:
            raise AudioFileNotFoundError()

        if not self._can_access_resource(
            creator_id=audio.created_by,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        signed_url = await self.cloudinary_client.generate_audio_signed_url(
            public_id=audio.audio_public_id,
            expiry_seconds=7200,
        )
        return AudioDetailResponse(audio=self._to_audio_record(audio), signed_url=signed_url)

    async def list_audio(
        self,
        *,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
        skip: int = 0,
        limit: int = 20,
    ) -> AudioListResponse:
        """List generated audio files with role-based scoping."""
        if is_super_admin(user_role) or is_org_admin(org_role):
            result = await self.audio_file_repo.list_by_organization(
                org_id=org_id,
                skip=skip,
                limit=limit,
            )
        else:
            result = await self.audio_file_repo.list_by_creator_and_organization(
                org_id=org_id,
                created_by=user_id,
                skip=skip,
                limit=limit,
            )

        return AudioListResponse(
            items=[self._to_audio_record(item) for item in result.items],
            total=result.total,
            skip=skip,
            limit=limit,
        )

    async def delete_audio(
        self,
        *,
        audio_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> None:
        """Delete generated audio with 3-tier access control."""
        audio = await self.audio_file_repo.find_by_id_and_org(audio_id=audio_id, org_id=org_id)
        if audio is None:
            raise AudioFileNotFoundError()

        if not self._can_access_resource(
            creator_id=audio.created_by,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        deleted = await self.audio_file_repo.soft_delete(audio_id=audio.id)
        if not deleted:
            raise AudioFileNotFoundError()

        delete_result = await self.cloudinary_client.delete_audio(audio.audio_public_id)
        if delete_result.get("result") not in {"ok", "not found"}:
            raise AppException("Audio storage delete failed")

    async def _validate_voice_access(
        self,
        *,
        voice_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> None:
        """Validate voice exists and caller has permission to use it."""
        cloned_voice = await self.voice_repo.find_by_minimax_voice_id(voice_id=voice_id, org_id=org_id)
        if cloned_voice is not None:
            if not self._can_access_resource(
                creator_id=cloned_voice.created_by,
                user_id=user_id,
                user_role=user_role,
                org_role=org_role,
            ):
                raise PermissionDeniedError()
            return

        system_voices = await self.minimax_client.list_voices(voice_type="system")
        for item in system_voices:
            if str(item.get("voice_id", "")) == voice_id:
                return
        raise VoiceNotFoundError()

    async def _persist_audio(
        self,
        *,
        audio_bytes: bytes,
        text: str,
        voice_id: str,
        org_id: str,
        user_id: str,
        duration_ms: int | None = None,
        size_bytes: int | None = None,
    ) -> GenerateAudioResponse:
        """Persist generated audio to Cloudinary and MongoDB."""
        timestamp_folder = datetime.now(timezone.utc).strftime("%Y-%m")
        unique_folder = f"{timestamp_folder}/{uuid4().hex}"
        upload_result = await self.cloudinary_client.upload_audio(
            file_bytes=audio_bytes,
            filename="tts-output.mp3",
            folder=unique_folder,
            org_id=org_id,
        )
        public_id = upload_result.get("public_id")
        audio_url = upload_result.get("secure_url") or upload_result.get("url")
        if not public_id or not audio_url:
            raise AppException("Audio storage failed")

        audio = await self.audio_file_repo.create(
            {
                "organization_id": org_id,
                "created_by": user_id,
                "voice_id": voice_id,
                "source_text": text,
                "audio_url": audio_url,
                "audio_public_id": public_id,
                "duration_ms": duration_ms if duration_ms is not None else 0,
                "size_bytes": size_bytes if size_bytes is not None else len(audio_bytes),
                "format": "mp3",
            }
        )
        signed_url = await self.cloudinary_client.generate_audio_signed_url(
            public_id=audio.audio_public_id,
            expiry_seconds=7200,
        )
        return GenerateAudioResponse(audio=self._to_audio_record(audio), signed_url=signed_url)

    @staticmethod
    def _validate_text(text: str) -> None:
        """Validate input text against TTS limits."""
        if not text or not text.strip():
            raise AppException("Text is required")
        if len(text) > 10000:
            raise AppException("Text must not exceed 10,000 characters")

    @staticmethod
    def _can_access_resource(
        *,
        creator_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_role: OrganizationRole | str | None,
    ) -> bool:
        """Apply 3-tier access control (super admin, org admin, owner)."""
        if is_super_admin(user_role):
            return True
        if is_org_admin(org_role):
            return True
        return creator_id == user_id

    @staticmethod
    def _to_audio_record(audio: AudioFile) -> AudioFileRecord:
        """Convert domain AudioFile model to API AudioFileRecord schema."""
        return AudioFileRecord(
            id=audio.id,
            organization_id=audio.organization_id,
            created_by=audio.created_by,
            voice_id=audio.voice_id,
            source_text=audio.source_text,
            audio_url=audio.audio_url,
            audio_public_id=audio.audio_public_id,
            duration_ms=audio.duration_ms,
            size_bytes=audio.size_bytes,
            format=audio.format,
            created_at=audio.created_at,
        )
