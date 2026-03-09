"""Image service for upload, retrieval, listing, and deletion logic."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import magic
from fastapi import UploadFile

from app.common.exceptions import (
    FileSizeLimitExceededError,
    ImageNotFoundError,
    ImageUploadError,
    InvalidImageTypeError,
    PermissionDeniedError,
)
from app.common.utils import is_org_admin, is_super_admin
from app.domain.models.image import Image
from app.domain.models.organization import OrganizationRole
from app.domain.models.user import UserRole
from app.domain.schemas.image import (
    ImageDetailResponse,
    ImageListResponse,
    ImageRecord,
    ImageUploadFailure,
    ImageUploadResponse,
)
from app.infrastructure.cloudinary.client import CloudinaryClient
from app.repo.image_repo import ImageRepository


class ImageService:
    """Service for image upload lifecycle and access control."""

    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
    READ_CHUNK_SIZE = 64 * 1024
    ALLOWED_MIME_TYPES = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/tiff",
        "image/bmp",
        "image/svg+xml",
    }

    def __init__(
        self,
        image_repo: ImageRepository,
        cloudinary_client: CloudinaryClient,
    ):
        """Initialize ImageService with repository and Cloudinary client."""
        self.image_repo = image_repo
        self.cloudinary_client = cloudinary_client

    async def validate_file(self, file: UploadFile) -> tuple[bytes, str, int]:
        """Validate file size and MIME type using streaming + magic bytes."""
        content = bytearray()
        total_size = 0

        while True:
            chunk = await file.read(self.READ_CHUNK_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > self.MAX_FILE_SIZE_BYTES:
                raise FileSizeLimitExceededError(
                    f"File '{file.filename}' exceeds 25MB limit"
                )
            content.extend(chunk)

        file_bytes = bytes(content)
        detected_mime = magic.from_buffer(file_bytes, mime=True)
        if detected_mime in {"text/plain", "text/xml"} and b"<svg" in file_bytes.lower():
            detected_mime = "image/svg+xml"

        if detected_mime not in self.ALLOWED_MIME_TYPES:
            raise InvalidImageTypeError(
                f"Unsupported image type '{detected_mime}' for file '{file.filename}'"
            )

        return file_bytes, detected_mime, total_size

    async def upload_images(
        self,
        files: list[UploadFile],
        user_id: str,
        org_id: str,
    ) -> ImageUploadResponse:
        """Upload multiple images concurrently with partial-failure support."""

        async def _process_file(file: UploadFile) -> tuple[ImageRecord | None, ImageUploadFailure | None]:
            try:
                file_bytes, detected_mime, size_bytes = await self.validate_file(file)

                timestamp_folder = datetime.now(timezone.utc).strftime("%Y-%m")
                unique_folder = f"{timestamp_folder}/{uuid4().hex}"

                upload_result = await self.cloudinary_client.upload(
                    file_bytes=file_bytes,
                    filename=file.filename or "uploaded-image",
                    folder=unique_folder,
                    org_id=org_id,
                )

                public_id = upload_result.get("public_id")
                if not public_id:
                    raise ImageUploadError(
                        f"Missing public_id from Cloudinary for file '{file.filename}'"
                    )

                cloudinary_folder = f"{org_id}/{unique_folder}"
                image = await self.image_repo.create(
                    {
                        "public_id": public_id,
                        "organization_id": org_id,
                        "uploaded_by": user_id,
                        "original_filename": file.filename or "uploaded-image",
                        "mime_type": detected_mime,
                        "size_bytes": size_bytes,
                        "cloudinary_folder": cloudinary_folder,
                    }
                )
                return self._to_image_record(image), None
            except (InvalidImageTypeError, FileSizeLimitExceededError, ImageUploadError) as exc:
                return None, ImageUploadFailure(
                    filename=file.filename or "unknown",
                    reason=exc.message,
                )
            except Exception as exc:  # noqa: BLE001
                return None, ImageUploadFailure(
                    filename=file.filename or "unknown",
                    reason=f"Upload failed: {exc}",
                )
            finally:
                await file.close()

        results = await asyncio.gather(*[_process_file(file) for file in files])

        uploaded_images: list[ImageRecord] = []
        failed_images: list[ImageUploadFailure] = []
        for image, failure in results:
            if image is not None:
                uploaded_images.append(image)
            if failure is not None:
                failed_images.append(failure)

        return ImageUploadResponse(
            uploaded=len(uploaded_images),
            failed=len(failed_images),
            images=uploaded_images,
            failures=failed_images,
        )

    async def get_image(
        self,
        image_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> ImageDetailResponse:
        """Get image metadata and generate a 2-hour signed URL."""
        is_super_admin_role = is_super_admin(user_role)
        is_org_admin_role = is_org_admin(org_role)

        if is_super_admin_role:
            image = await self.image_repo.find_by_id(image_id=image_id)
        else:
            image = await self.image_repo.find_by_id_and_org(
                image_id=image_id,
                org_id=org_id,
            )

        if image is None:
            raise ImageNotFoundError()

        is_owner = image.uploaded_by == user_id
        if not (is_owner or is_org_admin_role or is_super_admin_role):
            raise PermissionDeniedError()

        signed_url = await self.cloudinary_client.generate_signed_url(
            public_id=image.public_id,
            expiry_seconds=7200,
        )

        return ImageDetailResponse(
            image=self._to_image_record(image),
            signed_url=signed_url,
        )

    async def list_images(
        self,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
        skip: int = 0,
        limit: int = 20,
    ) -> ImageListResponse:
        """List images for an organization with pagination."""
        is_super_admin_role = is_super_admin(user_role)
        is_org_admin_role = is_org_admin(org_role)

        if is_super_admin_role or is_org_admin_role:
            result = await self.image_repo.list_by_organization(
                org_id=org_id,
                skip=skip,
                limit=limit,
            )
        else:
            result = await self.image_repo.list_by_uploader_and_organization(
                org_id=org_id,
                uploaded_by=user_id,
                skip=skip,
                limit=limit,
            )

        return ImageListResponse(
            items=[self._to_image_record(item) for item in result.items],
            total=result.total,
            skip=skip,
            limit=limit,
        )

    async def delete_image(
        self,
        image_id: str,
        user_id: str,
        user_role: UserRole | str,
        org_id: str,
        org_role: OrganizationRole | str | None,
    ) -> None:
        """Delete image with permission check and storage cleanup."""
        is_super_admin_role = is_super_admin(user_role)

        if is_super_admin_role:
            image = await self.image_repo.find_by_id(image_id)
        else:
            image = await self.image_repo.find_by_id_and_org(image_id=image_id, org_id=org_id)

        if image is None:
            raise ImageNotFoundError()

        is_owner = image.uploaded_by == user_id
        is_org_admin_role = is_org_admin(org_role)
        if not (is_owner or is_org_admin_role or is_super_admin_role):
            raise PermissionDeniedError()

        soft_deleted = await self.image_repo.soft_delete(image.id)
        if not soft_deleted:
            raise ImageNotFoundError()

        delete_result = await self.cloudinary_client.delete(image.public_id)
        if delete_result.get("result") not in {"ok", "not found"}:
            raise ImageUploadError("Failed to delete image from Cloudinary")

    def _to_image_record(self, image: Image) -> ImageRecord:
        """Convert domain Image model to API ImageRecord schema."""
        return ImageRecord(
            id=image.id,
            public_id=image.public_id,
            organization_id=image.organization_id,
            uploaded_by=image.uploaded_by,
            original_filename=image.original_filename,
            mime_type=image.mime_type,
            size_bytes=image.size_bytes,
            cloudinary_folder=image.cloudinary_folder,
            source=image.source,
            generation_job_id=image.generation_job_id,
            provider=image.provider,
            provider_model=image.provider_model,
            created_at=image.created_at,
        )
