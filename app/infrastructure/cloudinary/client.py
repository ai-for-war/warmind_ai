"""Cloudinary client wrapper for authenticated image operations."""

import asyncio
import time
from typing import Any

import cloudinary
import cloudinary.uploader  # type: ignore[import-untyped]
from cloudinary.utils import cloudinary_url  # type: ignore[import-untyped]

from app.config.settings import get_settings


class CloudinaryClient:
    """Async-friendly client for Cloudinary upload/delete/url operations."""

    _configured: bool = False

    @classmethod
    def configure(cls) -> None:
        """Initialize Cloudinary SDK configuration from application settings."""
        settings = get_settings()
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        cls._configured = True

    async def upload(
        self,
        file_bytes: bytes,
        filename: str,
        folder: str,
        org_id: str,
    ) -> dict[str, Any]:
        """Upload image bytes to Cloudinary using authenticated delivery."""
        if not self._configured:
            self.configure()

        target_folder = f"{org_id}/{folder}".strip("/")
        return await asyncio.to_thread(
            cloudinary.uploader.upload,
            file_bytes,
            resource_type="image",
            type="authenticated",
            folder=target_folder,
            filename_override=filename,
        )

    async def delete(self, public_id: str) -> dict[str, Any]:
        """Delete an image from Cloudinary and invalidate CDN cache."""
        if not self._configured:
            self.configure()

        return await asyncio.to_thread(
            cloudinary.uploader.destroy,
            public_id,
            resource_type="image",
            type="authenticated",
            invalidate=True,
        )

    async def generate_signed_url(
        self,
        public_id: str,
        expiry_seconds: int = 7200,
    ) -> str:
        """Generate a signed Cloudinary URL with a limited validity window."""
        if not self._configured:
            self.configure()

        expires_at = int(time.time()) + expiry_seconds

        def _generate() -> str:
            url, _ = cloudinary_url(
                public_id,
                resource_type="image",
                type="authenticated",
                sign_url=True,
                expires_at=expires_at,
                secure=True,
            )
            return url

        return await asyncio.to_thread(_generate)
