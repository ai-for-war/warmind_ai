"""Text-to-speech API endpoints."""

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.repo import get_member_repo
from app.common.service import get_tts_service
from app.common.utils import resolve_user_and_org_role
from app.domain.models.user import User
from app.domain.schemas.tts import (
    AudioDetailResponse,
    AudioListResponse,
    GenerateAudioRequest,
    GenerateAudioResponse,
    StreamAudioRequest,
    StreamAudioResponse,
)
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.services.tts.tts_service import TTSService

router = APIRouter(prefix="/tts", tags=["TTS"])


@router.post(
    "/stream",
    response_model=StreamAudioResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def stream_audio(
    request: StreamAudioRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    tts_service: TTSService = Depends(get_tts_service),
) -> StreamAudioResponse:
    """Trigger async TTS streaming over the shared Socket.IO connection."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    request_id = uuid4().hex

    background_tasks.add_task(
        tts_service.stream_audio_to_socket,
        request_id=request_id,
        text=request.text,
        voice_id=request.voice_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
        speed=request.speed,
        volume=request.volume,
        pitch=request.pitch,
        emotion=request.emotion,
    )

    return StreamAudioResponse(request_id=request_id)


@router.post("/generate", response_model=GenerateAudioResponse, status_code=status.HTTP_201_CREATED)
async def generate_audio(
    request: GenerateAudioRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    tts_service: TTSService = Depends(get_tts_service),
) -> GenerateAudioResponse:
    """Generate TTS audio synchronously and return persisted metadata."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await tts_service.generate_audio(
        text=request.text,
        voice_id=request.voice_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
        speed=request.speed,
        volume=request.volume,
        pitch=request.pitch,
        emotion=request.emotion,
    )


@router.get("/audio", response_model=AudioListResponse)
async def list_audio(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    tts_service: TTSService = Depends(get_tts_service),
) -> AudioListResponse:
    """List generated audio files visible to caller in the current organization."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await tts_service.list_audio(
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
        skip=skip,
        limit=limit,
    )


@router.get("/audio/{audio_id}", response_model=AudioDetailResponse)
async def get_audio(
    audio_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    tts_service: TTSService = Depends(get_tts_service),
) -> AudioDetailResponse:
    """Get generated audio metadata and signed URL."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await tts_service.get_audio(
        audio_id=audio_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )


@router.delete("/audio/{audio_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_audio(
    audio_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    tts_service: TTSService = Depends(get_tts_service),
) -> Response:
    """Delete generated audio if caller is owner, org admin, or super admin."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    await tts_service.delete_audio(
        audio_id=audio_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
