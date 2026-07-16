import re
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
from app.errors import not_found, bad_request
from app.repositories.project_repository import ProjectRepository
from app.repositories.chapter_repository import ChapterRepository
from app.models.project import ProjectDocument
from app.models.chapter import ChapterVersion


SCHEMA_VERSION = "1.0"
ENCODINGS = ["utf-8", "utf-8-sig", "gb18030"]
CHAPTER_PATTERNS = [
    re.compile(r"^第[零一二三四五六七八九十百千万\d]+[章节回卷](?!第).*$"),
    re.compile(r"^Chapter\s+\d+(?!.*\bChapter\b).*$", re.IGNORECASE),
]
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ImportExportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.chapter_repo = ChapterRepository(session)

    async def _read_upload(self, file: UploadFile) -> str:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise bad_request("FILE_TOO_LARGE", "文件超过 20 MB 限制")
        for enc in ENCODINGS:
            try:
                return content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise bad_request("UNSUPPORTED_ENCODING", "无法识别文件编码，请使用 UTF-8 或 GB18030")

    def _detect_chapters(self, text: str) -> list[dict]:
        lines = text.split("\n")
        chapters = []
        current_title = "未命名章节"

        for line in lines:
            stripped = line.strip()
            heading_clean = re.sub(r"^#+\s*", "", stripped)
            is_heading = any(p.match(heading_clean) for p in CHAPTER_PATTERNS)
            if is_heading:
                if chapters:
                    chapters[-1]["text"] = chapters[-1]["text"].rstrip("\n")
                chapters.append({"title": stripped, "text": ""})
                current_title = stripped
            else:
                if not chapters:
                    chapters.append({"title": current_title, "text": ""})
                chapters[-1]["text"] += line + "\n"

        if chapters:
            chapters[-1]["text"] = chapters[-1]["text"].rstrip("\n")
        return chapters

    async def preview_import(self, file: UploadFile) -> dict:
        text = await self._read_upload(file)
        chapters = self._detect_chapters(text)
        return {
            "total_chars": len(text),
            "total_chapters": len(chapters),
            "chapters": [
                {"title": ch["title"], "char_count": len(ch["text"])}
                for ch in chapters
            ],
            "chapters_data": chapters,
        }

    async def commit_import(self, project_id: str, chapters: list[dict]) -> list[dict]:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise not_found("PROJECT_NOT_FOUND", "小说项目不存在")

        created = []
        for data in chapters:
            chapter = await self.chapter_repo.create(
                project_id, {"title": data["title"], "current_text": data["text"]}
            )
            if data.get("text"):
                await self.chapter_repo.create_version(
                    chapter.id, data["text"], source="import", note="导入时创建"
                )
            created.append({
                "id": chapter.id,
                "title": chapter.title,
                "char_count": len(chapter.current_text),
            })
        await self.session.flush()
        return created

    async def export_txt(self, project_id: str) -> str:
        chapters = await self.chapter_repo.list_all(project_id)
        parts = []
        for ch in chapters:
            parts.append(ch.title)
            parts.append("")
            parts.append(ch.current_text)
            parts.append("")
        return "\n".join(parts)

    async def export_markdown(self, project_id: str) -> str:
        chapters = await self.chapter_repo.list_all(project_id)
        parts = []
        for ch in chapters:
            parts.append(f"# {ch.title}")
            parts.append("")
            parts.append(ch.current_text)
            parts.append("")
        return "\n".join(parts)

    async def export_json(self, project_id: str) -> dict:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise not_found("PROJECT_NOT_FOUND", "小说项目不存在")

        chapters = await self.chapter_repo.list_all(project_id)
        chapter_versions = {}
        for ch in chapters:
            versions = await self.chapter_repo.get_versions(ch.id)
            chapter_versions[ch.id] = [
                {
                    "version_number": v.version_number,
                    "source": v.source,
                    "text": v.text,
                    "note": v.note,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in versions
            ]

        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": _utcnow().isoformat(),
            "project": {
                "name": project.name,
                "genre": project.genre,
                "author_note": project.author_note,
                "default_pov": project.default_pov,
            },
            "documents": [
                {
                    "kind": doc.kind,
                    "title": doc.title,
                    "content": doc.content,
                }
                for doc in project.documents
            ],
            "chapters": [
                {
                    "title": ch.title,
                    "sort_order": ch.sort_order,
                    "current_text": ch.current_text,
                    "status": ch.status,
                    "versions": chapter_versions.get(ch.id, []),
                }
                for ch in chapters
            ],
        }

    async def import_project_bundle(self, file: UploadFile) -> dict:
        text = await self._read_upload(file)
        try:
            bundle = json.loads(text)
        except json.JSONDecodeError:
            raise bad_request("INVALID_JSON", "文件不是有效的 JSON")

        if "schema_version" not in bundle:
            raise bad_request("INVALID_BUNDLE", "文件缺少 schema_version，不是有效的项目导出包")

        project_data = bundle.get("project", {})
        project = await self.project_repo.create({
            "name": project_data.get("name", "导入项目"),
            "genre": project_data.get("genre", ""),
            "author_note": project_data.get("author_note", ""),
            "default_pov": project_data.get("default_pov", ""),
        })

        for doc in bundle.get("documents", []):
            await self.project_repo.update_document(
                project.id, doc["kind"],
                {"title": doc.get("title"), "content": doc.get("content", "")},
            )

        created_chapters = []
        for ch_data in bundle.get("chapters", []):
            chapter = await self.chapter_repo.create(project.id, {
                "title": ch_data["title"],
                "sort_order": ch_data.get("sort_order", 0),
                "current_text": ch_data.get("current_text", ""),
                "status": ch_data.get("status", "draft"),
            })
            for v_data in ch_data.get("versions", []):
                await self.chapter_repo.create_version(
                    chapter.id,
                    text=v_data["text"],
                    source=v_data.get("source", "import"),
                    note=v_data.get("note", ""),
                )
            created_chapters.append({"id": chapter.id, "title": chapter.title})

        await self.session.refresh(project, ["documents"])
        return {
            "project_id": project.id,
            "project_name": project.name,
            "chapters_imported": len(created_chapters),
        }
