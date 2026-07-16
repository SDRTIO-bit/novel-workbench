from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.project import Project, ProjectDocument, DOCUMENT_KINDS


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self, include_deleted: bool = False) -> list[Project]:
        stmt = select(Project).options(selectinload(Project.documents))
        if not include_deleted:
            stmt = stmt.where(Project.deleted_at.is_(None))
        stmt = stmt.order_by(Project.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, project_id: str) -> Project | None:
        stmt = select(Project).options(selectinload(Project.documents)).where(Project.id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Project:
        project = Project(**data)
        self.session.add(project)
        await self.session.flush()
        await self._create_default_documents(project.id)
        await self.session.refresh(project, ["documents"])
        return project

    async def _create_default_documents(self, project_id: str):
        for i, kind in enumerate(DOCUMENT_KINDS):
            doc = ProjectDocument(
                project_id=project_id,
                kind=kind,
                title=kind.capitalize(),
                content="",
                sort_order=i,
            )
            self.session.add(doc)
        await self.session.flush()

    async def duplicate(self, project_id: str, new_name: str) -> Project:
        original = await self.get_by_id(project_id)
        if not original:
            raise ValueError("Project not found")

        project = Project(
            name=new_name,
            genre=original.genre,
            author_note=original.author_note,
            default_pov=original.default_pov,
        )
        self.session.add(project)
        await self.session.flush()

        for doc in original.documents:
            new_doc = ProjectDocument(
                project_id=project.id,
                kind=doc.kind,
                title=doc.title,
                content=doc.content,
                sort_order=doc.sort_order,
            )
            self.session.add(new_doc)
        await self.session.flush()
        await self.session.refresh(project, ["documents"])
        return project

    async def get_documents(self, project_id: str) -> list[ProjectDocument]:
        stmt = (
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_document(self, project_id: str, kind: str) -> ProjectDocument | None:
        stmt = select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.kind == kind,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_document(self, project_id: str, kind: str, data: dict) -> ProjectDocument | None:
        doc = await self.get_document(project_id, kind)
        if not doc:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(doc, key, value)
        doc.updated_at = _utcnow()
        await self.session.flush()
        return doc
