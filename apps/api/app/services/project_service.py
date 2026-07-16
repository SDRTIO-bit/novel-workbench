from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import not_found
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    DocumentUpdate,
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.repo = ProjectRepository(session)

    async def list_projects(self):
        projects = await self.repo.list_all()
        return projects

    async def create_project(self, data: ProjectCreate):
        return await self.repo.create(data.model_dump())

    async def get_project(self, project_id: str):
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise not_found("PROJECT_NOT_FOUND", "小说项目不存在")
        return project

    async def update_project(self, project_id: str, data: ProjectUpdate):
        project = await self.get_project(project_id)
        updates = data.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(project, key, value)
        project.updated_at = _utcnow()
        return project

    async def delete_project(self, project_id: str):
        project = await self.get_project(project_id)
        project.deleted_at = _utcnow()
        return project

    async def restore_project(self, project_id: str):
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise not_found("PROJECT_NOT_FOUND", "小说项目不存在")
        project.deleted_at = None
        return project

    async def duplicate_project(self, project_id: str, new_name: str):
        await self.get_project(project_id)
        return await self.repo.duplicate(project_id, new_name)

    async def get_documents(self, project_id: str):
        await self.get_project(project_id)
        return await self.repo.get_documents(project_id)

    async def update_document(self, project_id: str, kind: str, data: DocumentUpdate):
        await self.get_project(project_id)
        doc = await self.repo.update_document(project_id, kind, data.model_dump(exclude_unset=True))
        if not doc:
            raise not_found("DOCUMENT_NOT_FOUND", "资料类型不存在")
        return doc
