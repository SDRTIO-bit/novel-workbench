from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.generation import (
    RunSchema, RunListSchema, CreateRunRequest,
    StageOverrideRequest, CandidateSchema, SelectIssuesRequest,
    AcceptFinalRequest,
)
from app.schemas.context import ContextPreviewRequest, ContextPreviewResponse
from app.services.generation_service import GenerationService
from app.services.context_service import ContextService

router = APIRouter(prefix="/api", tags=["runs"])


def _service(db: AsyncSession = Depends(get_db)) -> GenerationService:
    return GenerationService(db)


@router.post("/runs", response_model=RunSchema, status_code=201)
async def create_run(data: CreateRunRequest, svc: GenerationService = Depends(_service)):
    run = await svc.create_run(
        project_id=data.project_id,
        chapter_id=data.chapter_id,
        workflow_profile_id=data.workflow_profile_id,
        scene_instruction=data.scene_instruction,
    )
    await svc.session.commit()
    return run


@router.get("/runs/{run_id}", response_model=RunSchema)
async def get_run(run_id: str, svc: GenerationService = Depends(_service)):
    return await svc.get_run(run_id)


@router.get("/projects/{project_id}/runs", response_model=list[RunListSchema])
async def list_runs(project_id: str, svc: GenerationService = Depends(_service)):
    return await svc.list_runs(project_id)


@router.post("/runs/{run_id}/steps/{stage}/execute", response_model=CandidateSchema)
async def execute_stage(
    run_id: str, stage: str,
    override: StageOverrideRequest | None = None,
    svc: GenerationService = Depends(_service),
):
    ov = override.model_dump(exclude_none=True) if override else {}
    candidate = await svc.execute_stage(run_id, stage, ov)
    await svc.session.commit()
    return candidate


@router.post("/runs/{run_id}/steps/{stage}/preview", response_model=ContextPreviewResponse)
async def preview_stage(
    run_id: str, stage: str,
    override: StageOverrideRequest | None = None,
    svc: GenerationService = Depends(_service),
    db: AsyncSession = Depends(get_db),
):
    ov = override.model_dump(exclude_none=True) if override else {}
    ctx = await svc.preview_stage(run_id, stage, ov)
    return ContextPreviewResponse(**ctx)


@router.post("/runs/{run_id}/steps/{stage}/select/{candidate_id}")
async def select_candidate(
    run_id: str, stage: str, candidate_id: str,
    svc: GenerationService = Depends(_service),
):
    await svc.select_candidate(run_id, stage, candidate_id)
    await svc.session.commit()
    return {"status": "ok"}


@router.post("/runs/{run_id}/critic/select-issues")
async def select_critic_issues(
    run_id: str,
    data: SelectIssuesRequest,
    svc: GenerationService = Depends(_service),
):
    await svc.select_critic_issues(run_id, data.issue_ids, data.operation_by_issue)
    await svc.session.commit()
    return {"status": "ok"}


@router.post("/runs/{run_id}/accept")
async def accept_final_text(
    run_id: str,
    data: AcceptFinalRequest,
    svc: GenerationService = Depends(_service),
):
    result = await svc.accept_final_text(run_id, data.accept_type, data.final_text)
    await svc.session.commit()
    return result


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, svc: GenerationService = Depends(_service)):
    await svc.cancel_run(run_id)
    await svc.session.commit()
    return {"status": "ok"}
