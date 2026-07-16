from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowStepUpdate,
    WorkflowProfileSchema,
    WorkflowProfileListSchema,
    WorkflowStepSchema,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _service(db: AsyncSession = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


@router.get("", response_model=list[WorkflowProfileListSchema])
async def list_workflows(svc: WorkflowService = Depends(_service)):
    return await svc.list_profiles()


@router.post("", response_model=WorkflowProfileSchema, status_code=201)
async def create_workflow(data: WorkflowCreate, svc: WorkflowService = Depends(_service)):
    profile = await svc.create_profile(data.model_dump())
    await svc.session.commit()
    return profile


@router.get("/{profile_id}", response_model=WorkflowProfileSchema)
async def get_workflow(profile_id: str, svc: WorkflowService = Depends(_service)):
    return await svc.get_profile(profile_id)


@router.patch("/{profile_id}", response_model=WorkflowProfileSchema)
async def update_workflow(profile_id: str, data: WorkflowUpdate, svc: WorkflowService = Depends(_service)):
    profile = await svc.update_profile(profile_id, data.model_dump(exclude_none=True))
    await svc.session.commit()
    return profile


@router.post("/{profile_id}/duplicate", response_model=WorkflowProfileSchema, status_code=201)
async def duplicate_workflow(profile_id: str, svc: WorkflowService = Depends(_service)):
    profile = await svc.duplicate_profile(profile_id)
    await svc.session.commit()
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_workflow(profile_id: str, svc: WorkflowService = Depends(_service)):
    await svc.delete_profile(profile_id)
    await svc.session.commit()


@router.put("/{profile_id}/steps/{stage}", response_model=WorkflowStepSchema)
async def update_step(
    profile_id: str, stage: str, data: WorkflowStepUpdate, svc: WorkflowService = Depends(_service)
):
    step = await svc.update_step(profile_id, stage, data.model_dump(exclude_none=True))
    await svc.session.commit()
    return step


@router.post("/{profile_id}/set-default", response_model=WorkflowProfileSchema)
async def set_default_workflow(profile_id: str, svc: WorkflowService = Depends(_service)):
    profile = await svc.set_default(profile_id)
    await svc.session.commit()
    return profile
