"""Socket.IO AsyncServer setup and event handlers."""

import asyncio
import contextlib

import socketio
from pydantic import ValidationError

from app.common.event_socket import InterviewEvents, MeetingEvents, STTEvents
from app.common.repo import get_member_repo
from app.domain.schemas.meeting import (
    MeetingAudioMetadata,
    MeetingErrorPayload,
    MeetingFinalizeRequest,
    MeetingStartRequest,
    MeetingStopRequest,
)
from app.domain.schemas.stt import (
    STTAudioMetadata,
    STTErrorPayload,
    STTFinalizeRequest,
    STTStartRequest,
    STTStopRequest,
)
from app.socket_gateway.auth import authenticate
from app.socket_gateway.manager import get_server_manager
from app.services.meeting.session import MeetingSessionEvent, MeetingSessionEventKind
from app.services.stt.session import STTSessionEvent, STTSessionEventKind

# Get Redis manager (may be None if Redis not configured)
client_manager = get_server_manager()

# Socket.IO server instance with optional Redis manager
# When client_manager is None, Socket.IO operates in local-only mode
sio = socketio.AsyncServer(
    async_mode="asgi",
    # TODO 07/01/2026 Add allow orgin for verify domain
    cors_allowed_origins="*",  # Configure for production
    client_manager=client_manager,
)

_stt_listener_tasks: dict[str, asyncio.Task[None]] = {}
_meeting_listener_tasks: dict[str, asyncio.Task[None]] = {}


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> None:
    """Handle client connection.

    Authenticates JWT token and joins user to their personal room.
    Token can be provided via:
    - auth object: {"token": "jwt-string"}
    - query params: ?token=jwt-string (for Postman testing)

    Args:
        sid: Socket session ID
        environ: WSGI environ dict
        auth: Auth object from client, expected format: {"token": "jwt-string"}

    Raises:
        ConnectionRefusedError: If authentication fails
    """
    user_data = await authenticate(auth, environ)

    if user_data is None:
        raise ConnectionRefusedError("Unauthorized")

    user_id = user_data["user_id"]
    # Save user_id in socket session for later event handlers.
    await sio.save_session(sid, {"user_id": user_id})
    # Auto-join user to personal room
    await sio.enter_room(sid, f"user:{user_id}")


@sio.event
async def disconnect(sid: str) -> None:
    """Handle client disconnection.

    Socket.IO automatically removes the client from all rooms on disconnect.

    Args:
        sid: Socket session ID
    """
    session = await _get_socket_session(sid)
    user_id = session.get("user_id")
    organization_id = session.get("organization_id")
    stt_service = _get_stt_service()
    meeting_service = _get_meeting_service()

    stt_session = stt_service.get_session(sid)
    stt_org_id = stt_session.organization_id if stt_session is not None else organization_id
    emitted = await stt_service.handle_disconnect(sid)
    if user_id and emitted:
        await _emit_stt_session_events(
            user_id=user_id,
            organization_id=stt_org_id,
            events=emitted,
        )

    meeting_session = meeting_service.get_session(sid)
    meeting_org_id = (
        meeting_session.organization_id if meeting_session is not None else organization_id
    )
    emitted = await meeting_service.handle_disconnect(sid)
    if user_id and emitted:
        await _emit_meeting_session_events(
            user_id=user_id,
            organization_id=meeting_org_id,
            events=emitted,
        )

    await _cancel_stt_listener(sid)
    await _cancel_meeting_listener(sid)


@sio.on(STTEvents.START)
async def stt_start(sid: str, payload: dict) -> None:
    user_id, organization_id = await _get_stt_identity(sid)
    service = _get_stt_service()

    try:
        request = STTStartRequest.model_validate(payload)
        emitted = await service.start_session(
            sid=sid,
            user_id=user_id,
            stream_id=request.stream_id,
            conversation_id=request.conversation_id,
            organization_id=organization_id,
            language=request.language,
            channel_map=request.channel_map,
        )
    except Exception as exc:
        stream_id = payload.get("stream_id") if isinstance(payload, dict) else None
        await _emit_stt_error(
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _persist_socket_organization_id(sid, user_id, organization_id)
    await _emit_stt_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )
    _ensure_stt_listener_task(sid=sid, user_id=user_id)


@sio.on(STTEvents.AUDIO)
async def stt_audio(
    sid: str,
    metadata_payload: dict,
    audio_payload: bytes | bytearray | memoryview,
) -> None:
    user_id, organization_id = await _get_stt_identity(sid)
    service = _get_stt_service()

    try:
        metadata = STTAudioMetadata.model_validate(metadata_payload)
        _require_matching_session(
            sid=sid,
            stream_id=metadata.stream_id,
            conversation_id=metadata.conversation_id,
        )
        if not isinstance(audio_payload, (bytes, bytearray, memoryview)):
            raise ValueError("STT audio payload must be binary")

        emitted = await service.push_audio(
            sid=sid,
            stream_id=metadata.stream_id,
            chunk=bytes(audio_payload),
        )
    except Exception as exc:
        stream_id = (
            metadata_payload.get("stream_id")
            if isinstance(metadata_payload, dict)
            else None
        )
        await _emit_stt_error(
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_stt_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )


@sio.on(STTEvents.FINALIZE)
async def stt_finalize(sid: str, payload: dict) -> None:
    user_id, organization_id = await _get_stt_identity(sid)
    service = _get_stt_service()

    try:
        request = STTFinalizeRequest.model_validate(payload)
        _require_matching_session(sid=sid, stream_id=request.stream_id)
        emitted = await service.finalize_session(
            sid=sid,
            stream_id=request.stream_id,
        )
    except Exception as exc:
        stream_id = payload.get("stream_id") if isinstance(payload, dict) else None
        await _emit_stt_error(
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_stt_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )


@sio.on(STTEvents.STOP)
async def stt_stop(sid: str, payload: dict) -> None:
    user_id, organization_id = await _get_stt_identity(sid)
    service = _get_stt_service()

    try:
        request = STTStopRequest.model_validate(payload)
        _require_matching_session(sid=sid, stream_id=request.stream_id)
        emitted = await service.stop_session(
            sid=sid,
            stream_id=request.stream_id,
        )
    except Exception as exc:
        stream_id = payload.get("stream_id") if isinstance(payload, dict) else None
        await _emit_stt_error(
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_stt_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )
    await _cancel_stt_listener(sid)


@sio.on(MeetingEvents.START)
async def meeting_start(sid: str, payload: dict) -> None:
    user_id = await _get_authenticated_user_id(sid)
    service = _get_meeting_service()

    try:
        request = MeetingStartRequest.model_validate(payload)
        emitted = await service.start_session(
            sid=sid,
            user_id=user_id,
            organization_id=request.organization_id,
            stream_id=request.stream_id,
            title=request.title,
            language=request.language,
            source=request.source,
        )
    except Exception as exc:
        stream_id = payload.get("stream_id") if isinstance(payload, dict) else None
        organization_id = (
            payload.get("organization_id") if isinstance(payload, dict) else None
        )
        await _emit_meeting_error(
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_meeting_session_events(
        user_id=user_id,
        organization_id=request.organization_id,
        events=emitted,
    )
    _ensure_meeting_listener_task(sid=sid, user_id=user_id)


@sio.on(MeetingEvents.AUDIO)
async def meeting_audio(
    sid: str,
    metadata_payload: dict,
    audio_payload: bytes | bytearray | memoryview,
) -> None:
    user_id = await _get_authenticated_user_id(sid)
    service = _get_meeting_service()
    active_session = service.get_session(sid)
    organization_id = (
        active_session.organization_id if active_session is not None else None
    )

    try:
        metadata = MeetingAudioMetadata.model_validate(metadata_payload)
        if not isinstance(audio_payload, (bytes, bytearray, memoryview)):
            raise ValueError("Meeting audio payload must be binary")

        emitted = await service.push_audio(
            sid=sid,
            stream_id=metadata.stream_id,
            chunk=bytes(audio_payload),
        )
    except Exception as exc:
        stream_id = (
            metadata_payload.get("stream_id")
            if isinstance(metadata_payload, dict)
            else None
        )
        await _emit_meeting_error(
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_meeting_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )


@sio.on(MeetingEvents.FINALIZE)
async def meeting_finalize(sid: str, payload: dict) -> None:
    user_id = await _get_authenticated_user_id(sid)
    service = _get_meeting_service()
    active_session = service.get_session(sid)
    organization_id = (
        active_session.organization_id if active_session is not None else None
    )

    try:
        request = MeetingFinalizeRequest.model_validate(payload)
        emitted = await service.finalize_session(
            sid=sid,
            stream_id=request.stream_id,
        )
    except Exception as exc:
        stream_id = payload.get("stream_id") if isinstance(payload, dict) else None
        await _emit_meeting_error(
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_meeting_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )
    await _cancel_meeting_listener(sid)


@sio.on(MeetingEvents.STOP)
async def meeting_stop(sid: str, payload: dict) -> None:
    user_id = await _get_authenticated_user_id(sid)
    service = _get_meeting_service()
    active_session = service.get_session(sid)
    organization_id = (
        active_session.organization_id if active_session is not None else None
    )

    try:
        request = MeetingStopRequest.model_validate(payload)
        emitted = await service.stop_session(
            sid=sid,
            stream_id=request.stream_id,
        )
    except Exception as exc:
        stream_id = payload.get("stream_id") if isinstance(payload, dict) else None
        await _emit_meeting_error(
            sid=sid,
            user_id=user_id,
            organization_id=organization_id,
            stream_id=stream_id,
            error=exc,
        )
        return

    await _emit_meeting_session_events(
        user_id=user_id,
        organization_id=organization_id,
        events=emitted,
    )
    await _cancel_meeting_listener(sid)


async def _get_socket_session(sid: str) -> dict:
    try:
        session = await sio.get_session(sid)
    except KeyError:
        return {}
    return session or {}


async def _get_stt_identity(sid: str) -> tuple[str, str | None]:
    socket_session = await _get_socket_session(sid)
    user_id = socket_session.get("user_id")
    if not user_id:
        raise PermissionError("Socket session is not authenticated")
    organization_id = socket_session.get("organization_id")
    if organization_id is None:
        organization_id = await _resolve_socket_organization_id(user_id)
    return user_id, organization_id


async def _get_authenticated_user_id(sid: str) -> str:
    socket_session = await _get_socket_session(sid)
    user_id = socket_session.get("user_id")
    if not user_id:
        raise PermissionError("Socket session is not authenticated")
    return user_id


async def _persist_socket_organization_id(
    sid: str,
    user_id: str,
    organization_id: str | None,
) -> None:
    payload = {"user_id": user_id}
    if organization_id is not None:
        payload["organization_id"] = organization_id
    await sio.save_session(sid, payload)


async def _resolve_socket_organization_id(user_id: str) -> str | None:
    memberships = await get_member_repo().list_by_user(user_id=user_id, is_active=True)
    if len(memberships) == 1:
        return memberships[0].organization_id
    return None


def _require_matching_session(
    sid: str,
    stream_id: str,
    conversation_id: str | None = None,
) -> None:
    session = _get_stt_service().get_session(sid)
    if session is None:
        raise LookupError(
            "No active STT session for this socket. Interview sessions are "
            "process-local and require sticky-session routing."
        )
    if session.stream_id != stream_id:
        raise PermissionError("Socket does not own this STT stream")
    if conversation_id is not None and session.conversation_id != conversation_id:
        raise PermissionError("Socket does not own this interview conversation")


def _ensure_stt_listener_task(*, sid: str, user_id: str) -> None:
    existing = _stt_listener_tasks.get(sid)
    if existing is not None and not existing.done():
        return
    _stt_listener_tasks[sid] = asyncio.create_task(
        _run_stt_listener(sid=sid, user_id=user_id)
    )


async def _cancel_stt_listener(sid: str) -> None:
    task = _stt_listener_tasks.pop(sid, None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _ensure_meeting_listener_task(*, sid: str, user_id: str) -> None:
    existing = _meeting_listener_tasks.get(sid)
    if existing is not None and not existing.done():
        return
    _meeting_listener_tasks[sid] = asyncio.create_task(
        _run_meeting_listener(sid=sid, user_id=user_id)
    )


async def _cancel_meeting_listener(sid: str) -> None:
    task = _meeting_listener_tasks.pop(sid, None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _run_stt_listener(*, sid: str, user_id: str) -> None:
    service = _get_stt_service()
    try:
        while True:
            session = service.get_session(sid)
            if session is None:
                return

            emitted = await service.collect_session_events(
                sid=sid,
                wait_for_first=True,
                timeout_seconds=1.0,
            )
            if not emitted:
                timed_out_events = await service.reap_session(sid)
                if timed_out_events:
                    await _emit_stt_session_events(
                        user_id=user_id,
                        organization_id=session.organization_id,
                        events=timed_out_events,
                    )
                if service.get_session(sid) is None:
                    return
                continue

            await _emit_stt_session_events(
                user_id=user_id,
                organization_id=session.organization_id,
                events=emitted,
            )

            if service.get_session(sid) is None:
                return
    finally:
        _stt_listener_tasks.pop(sid, None)


async def _run_meeting_listener(*, sid: str, user_id: str) -> None:
    service = _get_meeting_service()
    try:
        while True:
            session = service.get_session(sid)
            if session is None:
                return

            emitted = await service.collect_session_events(
                sid=sid,
                wait_for_first=True,
                timeout_seconds=1.0,
            )
            if not emitted:
                if service.get_session(sid) is None:
                    return
                continue

            await _emit_meeting_session_events(
                user_id=user_id,
                organization_id=session.organization_id,
                events=emitted,
            )

            if service.get_session(sid) is None:
                return
    finally:
        _meeting_listener_tasks.pop(sid, None)


async def _emit_stt_session_events(
    *,
    user_id: str,
    organization_id: str | None,
    events: list[STTSessionEvent],
) -> None:
    if not events:
        return

    from app.socket_gateway import gateway

    event_names = {
        STTSessionEventKind.STARTED: STTEvents.STARTED,
        STTSessionEventKind.PARTIAL: STTEvents.PARTIAL,
        STTSessionEventKind.FINAL: STTEvents.FINAL,
        STTSessionEventKind.UTTERANCE_CLOSED: STTEvents.UTTERANCE_CLOSED,
        STTSessionEventKind.INTERVIEW_ANSWER: InterviewEvents.ANSWER,
        STTSessionEventKind.COMPLETED: STTEvents.COMPLETED,
        STTSessionEventKind.ERROR: STTEvents.ERROR,
    }

    for event in events:
        await gateway.emit_to_user(
            user_id=user_id,
            event=event_names[event.kind],
            data=event.payload.model_dump(exclude_none=True, by_alias=True),
            organization_id=organization_id,
        )


async def _emit_meeting_session_events(
    *,
    user_id: str,
    organization_id: str | None,
    events: list[MeetingSessionEvent],
) -> None:
    if not events:
        return

    from app.socket_gateway import gateway

    event_names = {
        MeetingSessionEventKind.STARTED: MeetingEvents.STARTED,
        MeetingSessionEventKind.FINAL: MeetingEvents.FINAL,
        MeetingSessionEventKind.UTTERANCE_CLOSED: MeetingEvents.UTTERANCE_CLOSED,
        MeetingSessionEventKind.COMPLETED: MeetingEvents.COMPLETED,
        MeetingSessionEventKind.INTERRUPTED: MeetingEvents.INTERRUPTED,
        MeetingSessionEventKind.ERROR: MeetingEvents.ERROR,
    }

    for event in events:
        await gateway.emit_to_user(
            user_id=user_id,
            event=event_names[event.kind],
            data=event.payload.model_dump(exclude_none=True, by_alias=True),
            organization_id=organization_id,
        )


async def _emit_stt_error(
    *,
    user_id: str,
    organization_id: str | None,
    stream_id: str | None,
    error: Exception,
) -> None:
    from app.socket_gateway import gateway

    error_message = (
        "Invalid STT payload"
        if isinstance(error, ValidationError)
        else str(error)
    )
    payload = STTErrorPayload(
        stream_id=stream_id,
        error_code="stt_request_error",
        error_message=error_message,
    )
    await gateway.emit_to_user(
        user_id=user_id,
        event=STTEvents.ERROR,
        data=payload.model_dump(exclude_none=True, by_alias=True),
        organization_id=organization_id,
    )


async def _emit_meeting_error(
    *,
    sid: str,
    user_id: str,
    organization_id: str | None,
    stream_id: str | None,
    error: Exception,
) -> None:
    from app.socket_gateway import gateway

    session = _get_meeting_service().get_session(sid)
    meeting_id = None
    if session is not None and (stream_id is None or session.stream_id == stream_id):
        meeting_id = session.meeting_id
    error_message = (
        "Invalid meeting payload"
        if isinstance(error, ValidationError)
        else str(error)
    )
    payload = MeetingErrorPayload(
        stream_id=stream_id,
        meeting_id=meeting_id,
        error_code="meeting_request_error",
        error_message=error_message,
    )
    await gateway.emit_to_user(
        user_id=user_id,
        event=MeetingEvents.ERROR,
        data=payload.model_dump(exclude_none=True, by_alias=True),
        organization_id=organization_id,
    )


def _get_stt_service():
    from app.common.service import get_stt_service

    return get_stt_service()


def _get_meeting_service():
    from app.common.service import get_meeting_service

    return get_meeting_service()
