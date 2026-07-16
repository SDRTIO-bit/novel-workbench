from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from fastapi.responses import PlainTextResponse, JSONResponse
from app.services.import_export_service import ImportExportService
import json

router = APIRouter(prefix="/api", tags=["import-export"])


def _service(db: AsyncSession = Depends(get_db)) -> ImportExportService:
    return ImportExportService(db)


@router.post("/import/preview")
async def preview_import(file: UploadFile = File(...), svc: ImportExportService = Depends(_service)):
    result = await svc.preview_import(file)
    chapters_data = result.pop("chapters_data")
    return {"preview": result, "chapters": chapters_data}


@router.post("/projects/{project_id}/import/commit")
async def commit_import(
    project_id: str,
    chapters: str = Form(...),
    svc: ImportExportService = Depends(_service),
):
    chapters_data = json.loads(chapters)
    created = await svc.commit_import(project_id, chapters_data)
    await svc.session.commit()
    return {"chapters": created}


@router.get("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    format: str = Query("json"),
    svc: ImportExportService = Depends(_service),
):
    if format == "txt":
        content = await svc.export_txt(project_id)
        return PlainTextResponse(content, media_type="text/plain; charset=utf-8")
    elif format == "md":
        content = await svc.export_markdown(project_id)
        return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")
    else:
        content = await svc.export_json(project_id)
        return JSONResponse(content)


@router.post("/import/project-bundle", status_code=201)
async def import_project_bundle(
    file: UploadFile = File(...),
    svc: ImportExportService = Depends(_service),
):
    result = await svc.import_project_bundle(file)
    await svc.session.commit()
    return result
