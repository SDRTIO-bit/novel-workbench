from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.chapter import (
    ChapterCreate,
    ChapterUpdate,
    ChapterReorder,
    ChapterSchema,
    ChapterListSchema,
    ChapterVersionSchema,
)
from app.services.chapter_service import ChapterService

router = APIRouter(tags=["chapters"])


def _service(db: AsyncSession = Depends(get_db)) -> ChapterService:
    return ChapterService(db)


@router.get("/api/projects/{project_id}/chapters", response_model=list[ChapterListSchema])
async def list_chapters(project_id: str, svc: ChapterService = Depends(_service)):
    return await svc.list_chapters(project_id)


@router.post("/api/projects/{project_id}/chapters", response_model=ChapterSchema, status_code=201)
async def create_chapter(project_id: str, data: ChapterCreate, svc: ChapterService = Depends(_service)):
    chapter = await svc.create_chapter(project_id, data)
    await svc.repo.session.commit()
    return chapter


@router.patch("/api/chapters/{chapter_id}", response_model=ChapterSchema)
async def update_chapter(chapter_id: str, data: ChapterUpdate, svc: ChapterService = Depends(_service)):
    chapter = await svc.update_chapter(chapter_id, data)
    await svc.repo.session.commit()
    return chapter


@router.delete("/api/chapters/{chapter_id}", status_code=204)
async def delete_chapter(chapter_id: str, svc: ChapterService = Depends(_service)):
    await svc.delete_chapter(chapter_id)
    await svc.repo.session.commit()


@router.post("/api/chapters/{chapter_id}/restore", response_model=ChapterSchema)
async def restore_chapter(chapter_id: str, svc: ChapterService = Depends(_service)):
    chapter = await svc.restore_chapter(chapter_id)
    await svc.repo.session.commit()
    return chapter


@router.post("/api/chapters/reorder", response_model=list[ChapterListSchema])
async def reorder_chapters(data: ChapterReorder, svc: ChapterService = Depends(_service)):
    chapters = await svc.reorder_chapters(data)
    await svc.repo.session.commit()
    return chapters


@router.get("/api/chapters/{chapter_id}/versions", response_model=list[ChapterVersionSchema])
async def get_versions(chapter_id: str, svc: ChapterService = Depends(_service)):
    return await svc.get_versions(chapter_id)


@router.post("/api/chapters/{chapter_id}/versions", response_model=ChapterVersionSchema, status_code=201)
async def create_version(chapter_id: str, note: str = "", svc: ChapterService = Depends(_service)):
    version = await svc.create_version(chapter_id, note=note, source="manual")
    await svc.repo.session.commit()
    return version


@router.post("/api/chapters/{chapter_id}/restore-version/{version_id}", response_model=ChapterSchema)
async def restore_version(chapter_id: str, version_id: str, svc: ChapterService = Depends(_service)):
    chapter = await svc.restore_version(chapter_id, version_id)
    await svc.repo.session.commit()
    return chapter
