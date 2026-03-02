"""Async client wrapper for MiniMax voice cloning and TTS APIs."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.common.exceptions import (
    MiniMaxAPIError,
    MiniMaxRateLimitError,
    MiniMaxStreamError,
)
from app.config.settings import get_settings


class MiniMaxClient:
    """Client for MiniMax HTTP APIs with connection pooling and SSE parsing."""

    BASE_URL = "https://api.minimax.io/v1"
    FILE_AND_CLONE_TIMEOUT = 30.0
    TTS_SYNC_TIMEOUT = 60.0
    TTS_STREAM_TIMEOUT = 120.0
    RATE_LIMIT_STATUS_CODES = {1002, 1039}

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
            timeout=self.TTS_SYNC_TIMEOUT,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        """Close underlying HTTP connections."""
        await self._client.aclose()

    async def upload_file(self, file_bytes: bytes, filename: str) -> int:
        """Upload source audio to MiniMax file API and return file_id."""
        files = {"file": (filename, file_bytes, "application/octet-stream")}
        data = {"purpose": "voice_clone"}

        try:
            response = await self._client.post(
                "/files/upload",
                data=data,
                files=files,
                timeout=self.FILE_AND_CLONE_TIMEOUT,
            )
            payload = self._parse_json_response(response, stream=False)
            file_id = self._extract_file_id(payload)
            if file_id is None:
                raise MiniMaxAPIError("MiniMax upload response missing file_id")
            return file_id
        except httpx.TimeoutException as exc:
            raise MiniMaxAPIError("MiniMax file upload timed out") from exc
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError("MiniMax file upload request failed") from exc

    async def clone_voice(
        self,
        file_id: int,
        voice_id: str,
        need_noise_reduction: bool = False,
        need_volume_normalization: bool = False,
    ) -> dict[str, Any]:
        """Clone a voice from uploaded file using MiniMax voice clone API."""
        payload = {
            "file_id": file_id,
            "voice_id": voice_id,
            "need_noise_reduction": need_noise_reduction,
            "need_volume_normalization": need_volume_normalization,
        }

        try:
            response = await self._client.post(
                "/voice_clone",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.FILE_AND_CLONE_TIMEOUT,
            )
            parsed = self._parse_json_response(response, stream=False)
            return parsed.get("data", parsed)
        except httpx.TimeoutException as exc:
            raise MiniMaxAPIError("MiniMax voice clone request timed out") from exc
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError("MiniMax voice clone request failed") from exc

    async def synthesize_sync(
        self,
        text: str,
        voice_id: str,
        *,
        model: str = "speech-2.8-hd",
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: int = 0,
        emotion: str | None = None,
        sample_rate: int = 32000,
        bitrate: int = 128000,
        audio_format: str = "mp3",
        channel: int = 1,
    ) -> dict[str, Any]:
        """Synthesize speech synchronously and return decoded MP3 bytes + metadata."""
        payload = self._build_t2a_payload(
            text=text,
            voice_id=voice_id,
            stream=False,
            model=model,
            speed=speed,
            vol=vol,
            pitch=pitch,
            emotion=emotion,
            sample_rate=sample_rate,
            bitrate=bitrate,
            audio_format=audio_format,
            channel=channel,
        )

        try:
            response = await self._client.post(
                "/t2a_v2",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.TTS_SYNC_TIMEOUT,
            )
            parsed = self._parse_json_response(response, stream=False)
            data = parsed.get("data", {})
            audio_hex = self._extract_audio_hex(data)
            if not audio_hex:
                raise MiniMaxAPIError("MiniMax synthesis response missing audio data")

            try:
                audio_bytes = bytes.fromhex(audio_hex)
            except ValueError as exc:
                raise MiniMaxAPIError("MiniMax returned invalid hex audio data") from exc

            usage = parsed.get("usage", {})
            usage_characters = (
                usage.get("total_characters")
                or usage.get("characters")
                or data.get("usage_characters")
            )
            duration_ms = data.get("duration_ms") or data.get("duration")

            return {
                "audio_bytes": audio_bytes,
                "duration_ms": duration_ms,
                "size_bytes": len(audio_bytes),
                "usage_characters": usage_characters,
                "raw": parsed,
            }
        except httpx.TimeoutException as exc:
            raise MiniMaxAPIError("MiniMax synchronous synthesis timed out") from exc
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError("MiniMax synchronous synthesis request failed") from exc

    async def synthesize_stream(
        self,
        text: str,
        voice_id: str,
        *,
        model: str = "speech-2.8-hd",
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: int = 0,
        emotion: str | None = None,
        sample_rate: int = 32000,
        bitrate: int = 128000,
        audio_format: str = "mp3",
        channel: int = 1,
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesized audio chunks decoded from MiniMax SSE events."""
        payload = self._build_t2a_payload(
            text=text,
            voice_id=voice_id,
            stream=True,
            model=model,
            speed=speed,
            vol=vol,
            pitch=pitch,
            emotion=emotion,
            sample_rate=sample_rate,
            bitrate=bitrate,
            audio_format=audio_format,
            channel=channel,
        )
        payload["stream_options"] = {"exclude_aggregated_audio": True}

        try:
            async with self._client.stream(
                "POST",
                "/t2a_v2",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.TTS_STREAM_TIMEOUT,
            ) as response:
                if response.status_code >= 400:
                    raise MiniMaxStreamError(
                        f"MiniMax stream request failed with HTTP {response.status_code}"
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue

                    raw_data = line[len("data:") :].strip()
                    if not raw_data or raw_data == "[DONE]":
                        continue

                    try:
                        event = json.loads(raw_data)
                    except json.JSONDecodeError as exc:
                        raise MiniMaxStreamError("Invalid MiniMax SSE payload") from exc

                    self._raise_for_base_resp(event, stream=True)

                    event_data = event.get("data", {})
                    audio_hex = self._extract_audio_hex(event_data)
                    if audio_hex:
                        try:
                            chunk = bytes.fromhex(audio_hex)
                        except ValueError as exc:
                            raise MiniMaxStreamError(
                                "MiniMax stream returned invalid hex audio chunk"
                            ) from exc
                        if chunk:
                            yield chunk

                    if event_data.get("status") == 2:
                        break
        except httpx.TimeoutException as exc:
            raise MiniMaxStreamError("MiniMax streaming synthesis timed out") from exc
        except httpx.HTTPError as exc:
            raise MiniMaxStreamError("MiniMax streaming synthesis request failed") from exc

    async def list_voices(self, voice_type: str = "all") -> list[dict[str, Any]]:
        """List voices from MiniMax get_voice API."""
        payload = {"voice_type": voice_type}

        try:
            response = await self._client.post(
                "/get_voice",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            parsed = self._parse_json_response(response, stream=False)
            data = parsed.get("data", {})
            voices = data.get("voices") or data.get("voice_list")
            return voices if isinstance(voices, list) else []
        except httpx.TimeoutException as exc:
            raise MiniMaxAPIError("MiniMax list voices request timed out") from exc
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError("MiniMax list voices request failed") from exc

    async def delete_voice(
        self,
        voice_id: str,
        voice_type: str = "voice_cloning",
    ) -> dict[str, Any]:
        """Delete a cloned voice on MiniMax."""
        payload = {"voice_type": voice_type, "voice_id": voice_id}

        try:
            response = await self._client.post(
                "/delete_voice",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            parsed = self._parse_json_response(response, stream=False)
            return parsed.get("data", parsed)
        except httpx.TimeoutException as exc:
            raise MiniMaxAPIError("MiniMax delete voice request timed out") from exc
        except httpx.HTTPError as exc:
            raise MiniMaxAPIError("MiniMax delete voice request failed") from exc

    @classmethod
    def _build_t2a_payload(
        cls,
        *,
        text: str,
        voice_id: str,
        stream: bool,
        model: str,
        speed: float,
        vol: float,
        pitch: int,
        emotion: str | None,
        sample_rate: int,
        bitrate: int,
        audio_format: str,
        channel: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "text": text,
            "stream": stream,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
            },
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": bitrate,
                "format": audio_format,
                "channel": channel,
            },
            "language_boost": "auto",
            "output_format": "hex",
        }
        if emotion:
            payload["voice_setting"]["emotion"] = emotion
        return payload

    def _parse_json_response(self, response: httpx.Response, *, stream: bool) -> dict[str, Any]:
        if response.status_code >= 400:
            if stream:
                raise MiniMaxStreamError(
                    f"MiniMax request failed with HTTP {response.status_code}"
                )
            raise MiniMaxAPIError(f"MiniMax request failed with HTTP {response.status_code}")

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            if stream:
                raise MiniMaxStreamError("MiniMax returned invalid JSON response") from exc
            raise MiniMaxAPIError("MiniMax returned invalid JSON response") from exc

        self._raise_for_base_resp(payload, stream=stream)
        return payload

    def _raise_for_base_resp(self, payload: dict[str, Any], *, stream: bool) -> None:
        base_resp = payload.get("base_resp")
        if not isinstance(base_resp, dict):
            return

        status_code = base_resp.get("status_code")
        if not isinstance(status_code, int) or status_code == 0:
            return

        status_msg = base_resp.get("status_msg") or "Unknown provider error"
        message = f"MiniMax error {status_code}: {status_msg}"

        if status_code in self.RATE_LIMIT_STATUS_CODES:
            raise MiniMaxRateLimitError(message, minimax_status_code=status_code)
        if stream:
            raise MiniMaxStreamError(message, minimax_status_code=status_code)
        raise MiniMaxAPIError(message, minimax_status_code=status_code)

    @staticmethod
    def _extract_file_id(payload: dict[str, Any]) -> int | None:
        data = payload.get("data", {})
        candidates = [
            payload.get("file_id"),
            data.get("file_id") if isinstance(data, dict) else None,
            payload.get("file", {}).get("file_id")
            if isinstance(payload.get("file"), dict)
            else None,
            data.get("file", {}).get("file_id")
            if isinstance(data, dict) and isinstance(data.get("file"), dict)
            else None,
        ]
        for value in candidates:
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    @staticmethod
    def _extract_audio_hex(data: dict[str, Any]) -> str | None:
        if not isinstance(data, dict):
            return None
        candidates = [
            data.get("audio"),
            data.get("audio_hex"),
            data.get("audio_data"),
            data.get("hex_audio"),
        ]
        for value in candidates:
            if isinstance(value, str):
                return value
        return None
