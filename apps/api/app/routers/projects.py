from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectSchema,
    ProjectListSchema,
    ProjectDocumentSchema,
    DocumentUpdate,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _service(db: AsyncSession = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


@router.get("", response_model=list[ProjectListSchema])
async def list_projects(svc: ProjectService = Depends(_service)):
    return await svc.list_projects()


@router.post("", response_model=ProjectSchema, status_code=201)
async def create_project(data: ProjectCreate, svc: ProjectService = Depends(_service)):
    project = await svc.create_project(data)
    await svc.repo.session.commit()
    return project


@router.get("/{project_id}", response_model=ProjectSchema)
async def get_project(project_id: str, svc: ProjectService = Depends(_service)):
    return await svc.get_project(project_id)


@router.patch("/{project_id}", response_model=ProjectSchema)
async def update_project(project_id: str, data: ProjectUpdate, svc: ProjectService = Depends(_service)):
    project = await svc.update_project(project_id, data)
    await svc.repo.session.commit()
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, svc: ProjectService = Depends(_service)):
    await svc.delete_project(project_id)
    await svc.repo.session.commit()


@router.post("/{project_id}/restore", response_model=ProjectSchema)
async def restore_project(project_id: str, svc: ProjectService = Depends(_service)):
    project = await svc.restore_project(project_id)
    await svc.repo.session.commit()
    return project


@router.post("/{project_id}/duplicate", response_model=ProjectSchema, status_code=201)
async def duplicate_project(project_id: str, svc: ProjectService = Depends(_service)):
    new_name = f"副本"
    project = await svc.duplicate_project(project_id, new_name)
    await svc.repo.session.commit()
    return project


@router.get("/{project_id}/documents", response_model=list[ProjectDocumentSchema])
async def get_documents(project_id: str, svc: ProjectService = Depends(_service)):
    return await svc.get_documents(project_id)


@router.put("/{project_id}/documents/{kind}", response_model=ProjectDocumentSchema)
async def update_document(project_id: str, kind: str, data: DocumentUpdate, svc: ProjectService = Depends(_service)):
    doc = await svc.update_document(project_id, kind, data)
    await svc.repo.session.commit()
    return doc
