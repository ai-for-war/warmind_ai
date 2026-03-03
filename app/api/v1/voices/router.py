"""Voice clone and management API endpoints."""

from fastapi import APIRouter, Depends, Form, Response, status, UploadFile

from app.api.deps import (
    OrganizationContext,
    get_current_active_user,
    get_current_organization_context,
)
from app.common.repo import get_member_repo
from app.common.service import get_voice_service
from app.common.utils import resolve_user_and_org_role
from app.domain.models.user import User
from app.domain.schemas.voice import (
    CloneVoiceResponse,
    PreviewVoiceRequest,
    VoiceDetailResponse,
    VoiceListResponse,
)
from app.repo.organization_member_repo import OrganizationMemberRepository
from app.services.voice.voice_service import VoiceService

router = APIRouter(prefix="/voices", tags=["Voices"])


@router.post("/clone", response_model=CloneVoiceResponse, status_code=status.HTTP_201_CREATED)
async def clone_voice(
    file: UploadFile,
    name: str = Form(..., min_length=1, max_length=255),
    voice_id: str = Form(
        ...,
        min_length=8,
        max_length=256,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{7,255}$",
    ),
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    voice_service: VoiceService = Depends(get_voice_service),
) -> CloneVoiceResponse:
    """Clone a new voice from uploaded source audio."""
    return await voice_service.clone_voice(
        file=file,
        name=name,
        voice_id=voice_id,
        user_id=current_user.id,
        org_id=org_context.organization_id,
    )


@router.get("", response_model=VoiceListResponse)
async def list_voices(
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    voice_service: VoiceService = Depends(get_voice_service),
) -> VoiceListResponse:
    """List system voices and cloned voices available to caller."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await voice_service.list_voices(
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )


@router.get("/{voice_id}", response_model=VoiceDetailResponse)
async def get_voice(
    voice_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    voice_service: VoiceService = Depends(get_voice_service),
) -> VoiceDetailResponse:
    """Get voice detail and signed source-audio URL (for cloned voice)."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    return await voice_service.get_voice(
        voice_id=voice_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_voice(
    voice_id: str,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    voice_service: VoiceService = Depends(get_voice_service),
) -> Response:
    """Delete cloned voice if caller is owner, org admin, or super admin."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    await voice_service.delete_voice(
        voice_id=voice_id,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{voice_id}/preview")
async def preview_voice(
    voice_id: str,
    request: PreviewVoiceRequest,
    current_user: User = Depends(get_current_active_user),
    org_context: OrganizationContext = Depends(get_current_organization_context),
    member_repo: OrganizationMemberRepository = Depends(get_member_repo),
    voice_service: VoiceService = Depends(get_voice_service),
) -> Response:
    """Synthesize a short preview and return raw MP3 bytes."""
    user_role, org_role = await resolve_user_and_org_role(
        current_user=current_user,
        organization_id=org_context.organization_id,
        member_repo=member_repo,
    )
    audio_bytes = await voice_service.preview_voice(
        voice_id=voice_id,
        text=request.text,
        user_id=current_user.id,
        user_role=user_role,
        org_id=org_context.organization_id,
        org_role=org_role,
    )
    return Response(content=audio_bytes, media_type="audio/mpeg")
