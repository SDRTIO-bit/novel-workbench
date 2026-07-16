from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.prompt import (
    PromptCreate,
    PromptVersionCreate,
    PromptProfileSchema,
    PromptProfileListSchema,
    PromptVersionSchema,
    RenderPreviewRequest,
    RenderPreviewResponse,
)
from app.services.prompt_service import PromptService

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _service(db: AsyncSession = Depends(get_db)) -> PromptService:
    return PromptService(db)


@router.get("", response_model=list[PromptProfileListSchema])
async def list_prompts(
    stage: str | None = Query(None),
    svc: PromptService = Depends(_service),
):
    return await svc.list_profiles(stage=stage)


@router.post("", response_model=PromptProfileSchema, status_code=201)
async def create_prompt(data: PromptCreate, svc: PromptService = Depends(_service)):
    profile = await svc.create_profile(data.model_dump())
    await svc.session.commit()
    return profile


@router.get("/{profile_id}/versions", response_model=list[PromptVersionSchema])
async def list_versions(profile_id: str, svc: PromptService = Depends(_service)):
    return await svc.get_versions(profile_id)


@router.post("/{profile_id}/versions", response_model=PromptVersionSchema, status_code=201)
async def add_version(
    profile_id: str, data: PromptVersionCreate, svc: PromptService = Depends(_service)
):
    version = await svc.add_version(profile_id, data.model_dump())
    await svc.session.commit()
    return version


@router.post("/{profile_id}/duplicate", response_model=PromptProfileSchema, status_code=201)
async def duplicate_prompt(profile_id: str, svc: PromptService = Depends(_service)):
    profile = await svc.duplicate_profile(profile_id)
    await svc.session.commit()
    return profile


@router.post("/{profile_id}/restore-default", response_model=PromptProfileSchema)
async def restore_default(profile_id: str, svc: PromptService = Depends(_service)):
    profile = await svc.restore_default(profile_id)
    await svc.session.commit()
    return profile


@router.post("/render-preview", response_model=RenderPreviewResponse)
async def render_preview(data: RenderPreviewRequest, svc: PromptService = Depends(_service)):
    system_prompt, user_prompt = await svc.render_preview(
        data.system_template, data.user_template, data.variables
    )
    return RenderPreviewResponse(system_prompt=system_prompt, user_prompt=user_prompt)


@router.get("/export")
async def export_prompts(svc: PromptService = Depends(_service)):
    return await svc.export_all()


@router.post("/import", status_code=201)
async def import_prompts(data: dict, svc: PromptService = Depends(_service)):
    count = await svc.import_profiles(data)
    await svc.session.commit()
    return {"imported": count}
