from app.mcp_utils import mcp_db
from app.services.chapter_service import ChapterService
from app.schemas.chapter import ChapterCreate, ChapterUpdate, ChapterReorder, ChapterReorderItem


async def list_chapters(project_id: str) -> list[dict]:
    """List all chapters in a project, ordered by sort_order."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        chapters = await svc.list_chapters(project_id)
        return [
            {
                "id": c.id,
                "title": c.title,
                "sort_order": c.sort_order,
                "status": c.status,
                "current_text_preview": _truncate(c.current_text, 200),
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in chapters
        ]


async def create_chapter(project_id: str, title: str = "新章节") -> dict:
    """Create a new chapter in a project."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        chapter = await svc.create_chapter(project_id, ChapterCreate(title=title))
        await session.commit()
        return {"id": chapter.id, "title": chapter.title, "sort_order": chapter.sort_order}


async def get_chapter(chapter_id: str) -> dict:
    """Get full chapter content and metadata."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        chapter = await svc.get_chapter(chapter_id)
        return {
            "id": chapter.id,
            "project_id": chapter.project_id,
            "title": chapter.title,
            "sort_order": chapter.sort_order,
            "current_text": chapter.current_text,
            "status": chapter.status,
            "updated_at": chapter.updated_at.isoformat() if chapter.updated_at else None,
        }


async def update_chapter(chapter_id: str, title: str | None = None, current_text: str | None = None) -> dict:
    """Update chapter title or content. WARNING: content update requires expected_updated_at from get_chapter."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        chapter = await svc.get_chapter(chapter_id)
        data = ChapterUpdate()
        data.expected_updated_at = chapter.updated_at
        if title is not None:
            data.title = title
        if current_text is not None:
            data.current_text = current_text
        result = await svc.update_chapter(chapter_id, data)
        await session.commit()
        return {"id": result.id, "updated_at": result.updated_at.isoformat()}


async def delete_chapter(chapter_id: str) -> dict:
    """Soft-delete a chapter."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        await svc.delete_chapter(chapter_id)
        await session.commit()
        return {"status": "deleted"}


async def restore_chapter(chapter_id: str) -> dict:
    """Restore a soft-deleted chapter."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        chapter = await svc.restore_chapter(chapter_id)
        await session.commit()
        return {"id": chapter.id, "title": chapter.title, "status": "restored"}


async def reorder_chapters(reorder_items: list[dict]) -> dict:
    """Reorder chapters. `reorder_items` is a list of {id, sort_order} dicts."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        items = [ChapterReorderItem(id=item["id"], sort_order=item["sort_order"]) for item in reorder_items]
        data = ChapterReorder(items=items)
        chapters = await svc.reorder_chapters(data)
        await session.commit()
        return {"reordered": len(chapters)}


async def restore_chapter_version(chapter_id: str, version_id: str) -> dict:
    """Restore chapter content to a previous version snapshot. Creates an auto-backup of current content first."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        chapter = await svc.restore_version(chapter_id, version_id)
        await session.commit()
        return {"id": chapter.id, "title": chapter.title, "updated_at": chapter.updated_at.isoformat()}


async def get_chapter_versions(chapter_id: str) -> list[dict]:
    """Get all saved versions of a chapter."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        versions = await svc.get_versions(chapter_id)
        return [
            {
                "id": v.id,
                "version_number": v.version_number,
                "source": v.source,
                "note": v.note,
                "text_preview": _truncate(v.text, 200),
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]


async def create_chapter_version(chapter_id: str, note: str = "") -> dict:
    """Save the current chapter content as a version snapshot."""
    async with mcp_db() as session:
        svc = ChapterService(session)
        version = await svc.create_version(chapter_id, note=note)
        await session.commit()
        return {"id": version.id, "version_number": version.version_number, "note": version.note}


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    return text[:max_len] + ("..." if len(text) > max_len else "")
