"""Dedicated MiniMax client for text-to-image generation."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.common.exceptions import (
    ImageGenerationNonRetryableProviderError,
    ImageGenerationRetryableProviderError,
)
from app.config.settings import get_settings


class MiniMaxImageGenerationResult(BaseModel):
    """Normalized provider response used by worker/service layers."""

    provider_trace_id: str | None = None
    images_base64: list[str] = Field(default_factory=list)
    success_count: int = 0
    failed_count: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


class MiniMaxImageClient:
    """Client for MiniMax text-to-image HTTP API."""

    BASE_URL = "https://api.minimax.io/v1"
    IMAGE_GENERATION_TIMEOUT = 90.0
    MODEL = "image-01"
    RESPONSE_FORMAT = "base64"
    OUTPUT_COUNT = 1
    RETRYABLE_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
    RETRYABLE_PROVIDER_CODES = {1000, 1001, 1002, 1024, 1033, 1039}
    NON_RETRYABLE_PROVIDER_CODES = {1004, 1008, 1026, 1027, 1042, 2013, 2049}

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        settings = get_settings()
        resolved_api_key = api_key or settings.MINIMAX_API_KEY
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {resolved_api_key}"},
            timeout=self.IMAGE_GENERATION_TIMEOUT,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        """Close underlying HTTP connections."""
        await self._client.aclose()

    async def generate_text_to_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str,
        seed: int | None = None,
        prompt_optimizer: bool = False,
    ) -> MiniMaxImageGenerationResult:
        """Call MiniMax image generation endpoint and normalize result."""
        payload = self._build_payload(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            seed=seed,
            prompt_optimizer=prompt_optimizer,
        )

        try:
            response = await self._client.post(
                "/image_generation",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.IMAGE_GENERATION_TIMEOUT,
            )
            parsed = self._parse_json_response(response)
            return self._normalize_response(parsed)
        except httpx.TimeoutException as exc:
            raise ImageGenerationRetryableProviderError(
                "Image generation provider timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageGenerationRetryableProviderError(
                "Image generation provider request failed"
            ) from exc

    @classmethod
    def _build_payload(
        cls,
        *,
        prompt: str,
        aspect_ratio: str,
        seed: int | None,
        prompt_optimizer: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": cls.MODEL,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": cls.RESPONSE_FORMAT,
            "n": cls.OUTPUT_COUNT,
            "prompt_optimizer": prompt_optimizer,
        }
        if seed is not None:
            payload["seed"] = seed
        return payload

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if status >= 400:
            if status in self.RETRYABLE_HTTP_STATUS_CODES:
                raise ImageGenerationRetryableProviderError(
                    "Image generation provider temporarily unavailable"
                )
            raise ImageGenerationNonRetryableProviderError(
                "Image generation request parameters were rejected"
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ImageGenerationRetryableProviderError(
                "Image generation provider returned invalid response"
            ) from exc

        self._raise_for_base_resp(payload)
        return payload

    def _raise_for_base_resp(self, payload: dict[str, Any]) -> None:
        base_resp = payload.get("base_resp")
        if not isinstance(base_resp, dict):
            return

        status_code = base_resp.get("status_code")
        if not isinstance(status_code, int) or status_code == 0:
            return

        status_msg = str(base_resp.get("status_msg") or "").lower()
        if status_code in self.NON_RETRYABLE_PROVIDER_CODES:
            raise ImageGenerationNonRetryableProviderError(
                provider_code=status_code,
            )

        if status_code in self.RETRYABLE_PROVIDER_CODES or any(
            keyword in status_msg
            for keyword in ("timeout", "temporary", "internal", "busy", "unavailable")
        ):
            raise ImageGenerationRetryableProviderError(
                provider_code=status_code,
            )

        raise ImageGenerationNonRetryableProviderError(
            provider_code=status_code,
        )

    @classmethod
    def _normalize_response(cls, payload: dict[str, Any]) -> MiniMaxImageGenerationResult:
        images = cls._extract_base64_images(payload)
        success_count = cls._extract_int(
            payload,
            keys=("success_count", "generated_count", "count_success"),
            default=len(images),
        )
        failed_count = cls._extract_int(
            payload,
            keys=("failed_count", "count_failed"),
            default=max(0, cls.OUTPUT_COUNT - success_count),
        )
        provider_trace_id = cls._extract_trace_id(payload)

        if not images:
            if failed_count > 0:
                raise ImageGenerationNonRetryableProviderError(
                    "Image generation request was blocked by provider policy"
                )
            raise ImageGenerationRetryableProviderError(
                "Image generation provider returned no image output"
            )

        return MiniMaxImageGenerationResult(
            provider_trace_id=provider_trace_id,
            images_base64=images,
            success_count=success_count,
            failed_count=failed_count,
            raw=payload,
        )

    @staticmethod
    def _extract_trace_id(payload: dict[str, Any]) -> str | None:
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}

        candidates = [
            payload.get("trace_id"),
            payload.get("request_id"),
            payload.get("id"),
            data.get("trace_id"),
            data.get("request_id"),
            data.get("id"),
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value
        return None

    @classmethod
    def _extract_base64_images(cls, payload: dict[str, Any]) -> list[str]:
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}

        # Official text-to-image response uses `data.image_base64`.
        # Keep one top-level fallback for minor provider payload drift.
        direct_candidates = [
            data.get("image_base64"),
            payload.get("image_base64"),
        ]
        images: list[str] = []
        for candidate in direct_candidates:
            images.extend(cls._collect_base64(candidate))

        # De-duplicate while preserving order.
        deduped: list[str] = []
        seen: set[str] = set()
        for image in images:
            if image in seen:
                continue
            seen.add(image)
            deduped.append(image)
        return deduped

    @classmethod
    def _collect_base64(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []

        if isinstance(value, dict):
            # Prefer official key; keep narrow aliases for compatibility only.
            candidates = [
                value.get("image_base64"),
                value.get("image"),
                value.get("b64_json"),
            ]
            images: list[str] = []
            for candidate in candidates:
                if isinstance(candidate, str) and candidate.strip():
                    images.append(candidate)
            return images

        if isinstance(value, list):
            images: list[str] = []
            for item in value:
                images.extend(cls._collect_base64(item))
            return images

        return []

    @staticmethod
    def _extract_int(
        payload: dict[str, Any],
        *,
        keys: tuple[str, ...],
        default: int,
    ) -> int:
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}

        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        for key in keys:
            for source in (payload, data, metadata):
                value = source.get(key)
                if isinstance(value, int):
                    return max(value, 0)
                if isinstance(value, str) and value.isdigit():
                    return int(value)
        return default
