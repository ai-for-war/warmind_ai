"""Voice service for clone, list, detail, delete, and preview operations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import magic
from fastapi import UploadFile

from app.common.exceptions import (
    AudioFileSizeLimitExceededError,
    AppException,
    InvalidAudioTypeError,
    MiniMaxAPIError,
    PermissionDeniedError,
    VoiceCloneError,
    VoiceNotFoundError,
)
from app.common.utils import is_org_admin, is_super_admin
from app.domain.models.organization import OrganizationRole
from app.domain.models.user import UserRole
from app.domain.models.voice import Voice, VoiceType
from app.domain.schemas.voice import (
    CloneVoiceResponse,
    SystemVoiceRecord,
    VoiceDetailResponse,
    VoiceListResponse,
    VoiceRecord,
)
from app.infrastructure.cloudinary.client import CloudinaryClient
from app.infrastructure.minimax.client import MiniMaxClient
from app.repo.voice_repo import VoiceRepository


class VoiceService:
    """Service for voice cloning lifecycle and access-controlled operations."""

    MAX_AUDIO_SIZE_BYTES = 20 * 1024 * 1024
    READ_CHUNK_SIZE = 64 * 1024
    ALLOWED_AUDIO_MIME_TYPES = {
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/wav",
        "audio/x-wav",
    }

    def __init__(
        self,
        voice_repo: VoiceRepository,
        cloudinary_client: CloudinaryClient,
        minimax_client: MiniMaxClient,
    ):
        """Initialize VoiceService with repository and provider clients."""
        self.voice_repo = voice_repo
        self.cloudinary_client = cloudinary_client
        self.minimax_client = minimax_client

    async def clone_voice(
        self,
        *,
        file: UploadFile,
        name: str,
        voice_id: str,
        user_id: str,
        org_id: str,
    ) -> CloneVoiceResponse:
        """Clone a voice from uploaded audio and persist metadata."""
        existing = await self.voice_repo.find_by_minimax_voice_id(
            voice_id=voice_id,
            org_id=org_id,
        )
        if existing is not None:
            raise AppException("voice_id is already in use")

        file_bytes, _detected_mime, _size_bytes = await self._validate_audio_file(file)
        cloudinary_public_id: str | None = None

        try:
            timestamp_folder = datetime.now(timezone.utc).strftime("%Y-%m")
            unique_folder = f"{timestamp_folder}/{uuid4().hex}"
            upload_result = await self.cloudinary_client.upload_audio(
                file_bytes=file_bytes,
                filename=file.filename or "voice-source-audio",
                folder=unique_folder,
                org_id=org_id,
            )
            cloudinary_public_id = upload_result.get("public_id")
            source_audio_url = upload_result.get("secure_url") or upload_result.get(
                "url"
            )

            if not cloudinary_public_id or not source_audio_url:
                raise VoiceCloneError("Failed to upload source audio to Cloudinary")

            minimax_file_id = await self.minimax_client.upload_file(
                file_bytes=file_bytes,
                filename=file.filename or "voice-source-audio",
            )
            clone_data = await self.minimax_client.clone_voice(
                file_id=minimax_file_id,
                voice_id=voice_id,
                # need_noise_reduction=True,
                # need_volume_normalization=True,
            )

            voice = await self.voice_repo.create(
                {
                    "voice_id": voice_id,
                    "name": name,
                    "voice_type": VoiceType.CLONED.value,
                    "organization_id": org_id,
                    "created_by": user_id,
                    "source_audio_url": source_audio_url,
                    "source_audio_public_id": cloudinary_public_id,
                    "language": clone_data.get("language"),
                }
            )

            return CloneVoiceResponse(
                voice=self._to_voice_record(voice),
                preview_url=clone_data.get("demo_audio"),
            )
        except MiniMaxAPIError as exc:
            if cloudinary_public_id:
                await self._safe_cleanup_source_audio(cloudinary_public_id)
            raise VoiceCloneError(exc.message) from exc
        finally:
            await file.close()

    async def list_voices(
        self,
        *,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
        skip: int = 0,
        limit: int = 100,
    ) -> VoiceListResponse:
        """List system voices and organization-scoped cloned voices."""
        system_voice_data = await self.minimax_client.list_voices(voice_type="system")
        system_voices = [
            self._to_system_voice_record(item) for item in system_voice_data
        ]

        if is_super_admin(user_role) or is_org_admin(org_role):
            cloned = await self.voice_repo.list_by_organization(
                org_id=org_id,
                skip=skip,
                limit=limit,
            )
        else:
            cloned = await self.voice_repo.list_by_creator_and_organization(
                org_id=org_id,
                created_by=user_id,
                skip=skip,
                limit=limit,
            )

        return VoiceListResponse(
            system_voices=system_voices,
            cloned_voices=[self._to_voice_record(item) for item in cloned.items],
            total_cloned=cloned.total,
        )

    async def get_voice(
        self,
        *,
        voice_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> VoiceDetailResponse:
        """Get cloned voice details with access control and signed source URL."""
        voice = await self.voice_repo.find_by_minimax_voice_id(
            voice_id=voice_id, org_id=org_id
        )
        if voice is None:
            raise VoiceNotFoundError()

        if not self._can_access_voice(
            voice=voice,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        signed_url = await self.cloudinary_client.generate_audio_signed_url(
            public_id=voice.source_audio_public_id,
            expiry_seconds=7200,
        )
        return VoiceDetailResponse(
            voice=self._to_voice_record(voice),
            source_audio_signed_url=signed_url,
        )

    async def delete_voice(
        self,
        *,
        voice_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> None:
        """Delete cloned voice with soft-delete and provider cleanup."""
        voice = await self.voice_repo.find_by_minimax_voice_id(
            voice_id=voice_id, org_id=org_id
        )
        if voice is None:
            raise VoiceNotFoundError()

        if not self._can_access_voice(
            voice=voice,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        deleted = await self.voice_repo.soft_delete(voice.id)
        if not deleted:
            raise VoiceNotFoundError()

        await self.minimax_client.delete_voice(voice_id=voice.voice_id)
        delete_result = await self.cloudinary_client.delete_audio(
            voice.source_audio_public_id
        )
        if delete_result.get("result") not in {"ok", "not found"}:
            raise VoiceCloneError("Failed to delete source audio from Cloudinary")

    async def preview_voice(
        self,
        *,
        voice_id: str,
        text: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> bytes:
        """Synthesize and return preview MP3 bytes without persistence."""
        if len(text) > 200:
            raise AppException("Preview text must not exceed 200 characters")

        voice = await self.voice_repo.find_by_minimax_voice_id(
            voice_id=voice_id, org_id=org_id
        )
        if voice is not None and not self._can_access_voice(
            voice=voice,
            user_id=user_id,
            user_role=user_role,
            org_role=org_role,
        ):
            raise PermissionDeniedError()

        response = await self.minimax_client.synthesize_sync(
            text=text, voice_id=voice_id
        )
        return response["audio_bytes"]

    async def _validate_audio_file(self, file: UploadFile) -> tuple[bytes, str, int]:
        """Validate uploaded audio file by size and magic-byte MIME detection."""
        content = bytearray()
        total_size = 0

        while True:
            chunk = await file.read(self.READ_CHUNK_SIZE)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > self.MAX_AUDIO_SIZE_BYTES:
                raise AudioFileSizeLimitExceededError(
                    f"File '{file.filename}' exceeds 20MB limit"
                )
            content.extend(chunk)

        file_bytes = bytes(content)
        detected_mime = magic.from_buffer(file_bytes, mime=True)
        if detected_mime not in self.ALLOWED_AUDIO_MIME_TYPES:
            raise InvalidAudioTypeError(
                f"Unsupported audio type '{detected_mime}' for file '{file.filename}'"
            )

        return file_bytes, detected_mime, total_size

    async def _safe_cleanup_source_audio(self, public_id: str) -> None:
        """Best-effort cleanup for uploaded source audio during clone failure."""
        try:
            await self.cloudinary_client.delete_audio(public_id)
        except Exception:  # noqa: BLE001
            return

    def _can_access_voice(
        self,
        *,
        voice: Voice,
        user_id: str,
        user_role: UserRole | str,
        org_role: OrganizationRole | str | None,
    ) -> bool:
        """Check 3-tier access control for cloned voice records."""
        if is_super_admin(user_role):
            return True
        if is_org_admin(org_role):
            return True
        return voice.created_by == user_id

    def _to_voice_record(self, voice: Voice) -> VoiceRecord:
        """Convert domain Voice model to API VoiceRecord schema."""
        return VoiceRecord(
            id=voice.id,
            voice_id=voice.voice_id,
            name=voice.name,
            voice_type=voice.voice_type,
            organization_id=voice.organization_id,
            created_by=voice.created_by,
            source_audio_url=voice.source_audio_url,
            source_audio_public_id=voice.source_audio_public_id,
            language=voice.language,
            created_at=voice.created_at,
        )

    def _to_system_voice_record(self, data: dict) -> SystemVoiceRecord:
        """Convert MiniMax voice entry to SystemVoiceRecord."""
        created_time = self._parse_created_time(data.get("created_time"))
        return SystemVoiceRecord(
            voice_id=str(data.get("voice_id") or ""),
            voice_name=str(data.get("voice_name") or data.get("name") or ""),
            description=self._normalize_minimax_description(data.get("description")),
            created_time=created_time,
        )

    @staticmethod
    def _normalize_minimax_description(value: object) -> list[str]:
        """Normalize MiniMax `description` field to the documented array-of-strings form."""
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, str):
                    text = item.strip()
                else:
                    text = str(item).strip()
                if text:
                    items.append(text)
            return items
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _parse_created_time(value: object) -> datetime | None:
        """Parse MiniMax created_time (seconds/ms epoch or ISO string)."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000.0
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None
