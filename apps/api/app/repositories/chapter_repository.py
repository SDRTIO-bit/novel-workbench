from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.chapter import Chapter, ChapterVersion, CHAPTER_VERSION_SOURCES


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChapterRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self, project_id: str, include_deleted: bool = False) -> list[Chapter]:
        stmt = select(Chapter).where(Chapter.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(Chapter.deleted_at.is_(None))
        stmt = stmt.order_by(Chapter.sort_order, Chapter.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, chapter_id: str) -> Chapter | None:
        stmt = select(Chapter).where(Chapter.id == chapter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, project_id: str, data: dict) -> Chapter:
        if "sort_order" not in data or data["sort_order"] == 0:
            max_order = await self._max_sort_order(project_id)
            data["sort_order"] = max_order + 1
        chapter = Chapter(project_id=project_id, **data)
        self.session.add(chapter)
        await self.session.flush()
        return chapter

    async def update(self, chapter: Chapter, data: dict) -> Chapter:
        for key, value in data.items():
            if key == "expected_updated_at":
                continue
            if value is not None:
                setattr(chapter, key, value)
        chapter.updated_at = _utcnow()
        await self.session.flush()
        return chapter

    async def delete(self, chapter: Chapter) -> Chapter:
        chapter.deleted_at = _utcnow()
        return chapter

    async def restore(self, chapter: Chapter) -> Chapter:
        chapter.deleted_at = None
        return chapter

    async def reorder(self, items: list[dict]) -> list[Chapter]:
        chapter_ids = [item["id"] for item in items]
        stmt = select(Chapter).where(Chapter.id.in_(chapter_ids))
        result = await self.session.execute(stmt)
        chapters = {c.id: c for c in result.scalars().all()}
        for item in items:
            if item["id"] in chapters:
                chapters[item["id"]].sort_order = item["sort_order"]
        await self.session.flush()
        return list(chapters.values())

    async def _max_sort_order(self, project_id: str) -> int:
        stmt = select(func.coalesce(func.max(Chapter.sort_order), 0)).where(
            Chapter.project_id == project_id,
            Chapter.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_versions(self, chapter_id: str) -> list[ChapterVersion]:
        stmt = (
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter_id)
            .order_by(ChapterVersion.version_number.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version_number(self, chapter_id: str) -> int:
        stmt = select(func.coalesce(func.max(ChapterVersion.version_number), 0)).where(
            ChapterVersion.chapter_id == chapter_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() + 1

    async def create_version(
        self,
        chapter_id: str,
        text: str,
        source: str = "manual",
        note: str = "",
        generation_candidate_id: str | None = None,
    ) -> ChapterVersion:
        version_number = await self.get_next_version_number(chapter_id)
        version = ChapterVersion(
            chapter_id=chapter_id,
            version_number=version_number,
            source=source,
            text=text,
            note=note,
            generation_candidate_id=generation_candidate_id,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_version(self, version_id: str) -> ChapterVersion | None:
        stmt = select(ChapterVersion).where(ChapterVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
