from app.mcp_utils import mcp_db
from app.services.project_service import ProjectService
from app.schemas.project import ProjectCreate, ProjectUpdate, DocumentUpdate
from app.errors import not_found


async def list_projects() -> list[dict]:
    """List all novel projects. Returns id, name, genre, status for each project."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        projects = await svc.list_projects()
        return [
            {
                "id": p.id,
                "name": p.name,
                "genre": p.genre,
                "author_note": p.author_note,
                "default_pov": p.default_pov,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in projects
        ]


async def create_project(
    name: str,
    genre: str = "",
    author_note: str = "",
    default_pov: str = "",
) -> dict:
    """Create a new novel project."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        project = await svc.create_project(ProjectCreate(
            name=name, genre=genre, author_note=author_note, default_pov=default_pov
        ))
        await session.commit()
        return {"id": project.id, "name": project.name, "genre": project.genre}


async def get_project(project_id: str) -> dict:
    """Get detailed info for a single project."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        project = await svc.get_project(project_id)
        return {
            "id": project.id,
            "name": project.name,
            "genre": project.genre,
            "author_note": project.author_note,
            "default_pov": project.default_pov,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }


async def update_project(
    project_id: str,
    name: str | None = None,
    genre: str | None = None,
    author_note: str | None = None,
    default_pov: str | None = None,
) -> dict:
    """Update an existing project. Only fields provided will be changed."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        data = ProjectUpdate()
        if name is not None:
            data.name = name
        if genre is not None:
            data.genre = genre
        if author_note is not None:
            data.author_note = author_note
        if default_pov is not None:
            data.default_pov = default_pov
        project = await svc.update_project(project_id, data)
        await session.commit()
        return {"id": project.id, "name": project.name, "updated_at": project.updated_at.isoformat()}


async def delete_project(project_id: str) -> dict:
    """Soft-delete a project."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        project = await svc.delete_project(project_id)
        await session.commit()
        return {"id": project.id, "status": "deleted"}


async def restore_project(project_id: str) -> dict:
    """Restore a soft-deleted project."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        project = await svc.restore_project(project_id)
        await session.commit()
        return {"id": project.id, "name": project.name, "status": "restored"}


async def get_project_documents(project_id: str) -> list[dict]:
    """Get all documents for a project (synopsis, outline, characters, world, etc.)."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        docs = await svc.get_documents(project_id)
        return [
            {"id": d.id, "kind": d.kind, "title": d.title, "content": d.content, "sort_order": d.sort_order}
            for d in docs
        ]


async def update_project_document(
    project_id: str,
    kind: str,
    title: str | None = None,
    content: str | None = None,
) -> dict:
    """Update a project document by kind (e.g. 'synopsis', 'outline')."""
    async with mcp_db() as session:
        svc = ProjectService(session)
        data = DocumentUpdate()
        if title is not None:
            data.title = title
        if content is not None:
            data.content = content
        doc = await svc.update_document(project_id, kind, data)
        await session.commit()
        return {"id": doc.id, "kind": doc.kind, "title": doc.title}
