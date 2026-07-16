from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.context import ContextPreviewRequest, ContextPreviewResponse
from app.services.context_service import ContextService

router = APIRouter(prefix="/api/context", tags=["context"])


def _service(db: AsyncSession = Depends(get_db)) -> ContextService:
    return ContextService(db)


@router.post("/preview", response_model=ContextPreviewResponse)
async def preview_context(data: ContextPreviewRequest, svc: ContextService = Depends(_service)):
    result = await svc.assemble(data)
    return ContextPreviewResponse(**result)
