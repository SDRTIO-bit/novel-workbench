from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import not_found, conflict
from app.repositories.chapter_repository import ChapterRepository
from app.schemas.chapter import (
    ChapterCreate,
    ChapterUpdate,
    ChapterReorder,
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChapterService:
    def __init__(self, session: AsyncSession):
        self.repo = ChapterRepository(session)

    async def list_chapters(self, project_id: str):
        return await self.repo.list_all(project_id)

    async def create_chapter(self, project_id: str, data: ChapterCreate):
        return await self.repo.create(project_id, data.model_dump())

    async def get_chapter(self, chapter_id: str):
        chapter = await self.repo.get_by_id(chapter_id)
        if not chapter:
            raise not_found("CHAPTER_NOT_FOUND", "章节不存在")
        return chapter

    async def update_chapter(self, chapter_id: str, data: ChapterUpdate):
        chapter = await self.get_chapter(chapter_id)
        if chapter.updated_at != data.expected_updated_at:
            raise conflict(
                "CHAPTER_EDIT_CONFLICT",
                "章节已被其他操作修改，请刷新后重试",
                {"server_current_text": chapter.current_text, "server_updated_at": chapter.updated_at.isoformat()},
            )
        return await self.repo.update(chapter, data.model_dump(exclude_unset=True))

    async def delete_chapter(self, chapter_id: str):
        chapter = await self.get_chapter(chapter_id)
        await self.repo.delete(chapter)

    async def restore_chapter(self, chapter_id: str):
        chapter = await self.repo.get_by_id(chapter_id)
        if not chapter:
            raise not_found("CHAPTER_NOT_FOUND", "章节不存在")
        await self.repo.restore(chapter)
        return chapter

    async def reorder_chapters(self, data: ChapterReorder):
        return await self.repo.reorder([item.model_dump() for item in data.items])

    async def get_versions(self, chapter_id: str):
        await self.get_chapter(chapter_id)
        return await self.repo.get_versions(chapter_id)

    async def create_version(self, chapter_id: str, note: str = "", source: str = "manual"):
        chapter = await self.get_chapter(chapter_id)
        version = await self.repo.create_version(
            chapter_id=chapter.id,
            text=chapter.current_text,
            source=source,
            note=note,
        )
        return version

    async def restore_version(self, chapter_id: str, version_id: str):
        chapter = await self.get_chapter(chapter_id)
        target = await self.repo.get_version(version_id)
        if not target or target.chapter_id != chapter_id:
            raise not_found("VERSION_NOT_FOUND", "版本不存在")

        await self.repo.create_version(
            chapter_id=chapter.id,
            text=chapter.current_text,
            source="restore_backup",
            note=f"恢复版本 v{target.version_number} 前的自动备份",
        )
        chapter.current_text = target.text
        chapter.updated_at = _utcnow()
        await self.repo.session.flush()
        return chapter
