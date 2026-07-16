from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas.provider import (
    ProviderCreate,
    ProviderUpdate,
    ProviderModelCreate,
    ProviderModelUpdate,
    ProviderSchema,
    ProviderModelSchema,
    TestConnectionResponse,
)
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _service(db: AsyncSession = Depends(get_db)) -> ProviderService:
    return ProviderService(db)


@router.get("", response_model=list[ProviderSchema])
async def list_providers(svc: ProviderService = Depends(_service)):
    return await svc.list_providers()


@router.post("", response_model=ProviderSchema, status_code=201)
async def create_provider(data: ProviderCreate, svc: ProviderService = Depends(_service)):
    provider = await svc.create_provider(data.model_dump())
    await svc.session.commit()
    return provider


@router.patch("/{provider_id}", response_model=ProviderSchema)
async def update_provider(provider_id: str, data: ProviderUpdate, svc: ProviderService = Depends(_service)):
    payload = data.model_dump(exclude_none=True)
    if data.api_key is not None and data.api_key == "":
        payload.pop("api_key", None)
    provider = await svc.update_provider(provider_id, payload)
    await svc.session.commit()
    return provider


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, svc: ProviderService = Depends(_service)):
    await svc.delete_provider(provider_id)
    await svc.session.commit()


@router.post("/{provider_id}/test", response_model=TestConnectionResponse)
async def test_connection(provider_id: str, svc: ProviderService = Depends(_service)):
    return await svc.test_connection(provider_id)


@router.post("/{provider_id}/sync-models", response_model=ProviderSchema)
async def sync_models(provider_id: str, svc: ProviderService = Depends(_service)):
    await svc.sync_models(provider_id)
    await svc.session.commit()
    provider = await svc._get_provider(provider_id)
    return provider


@router.post("/{provider_id}/models", response_model=ProviderModelSchema, status_code=201)
async def add_model(provider_id: str, data: ProviderModelCreate, svc: ProviderService = Depends(_service)):
    model = await svc.add_model(provider_id, data.model_dump())
    await svc.session.commit()
    return model


@router.patch("/{provider_id}/models/{model_id}", response_model=ProviderModelSchema)
async def update_model(
    provider_id: str,
    model_id: str,
    data: ProviderModelUpdate,
    svc: ProviderService = Depends(_service),
):
    model = await svc.update_model(provider_id, model_id, data.model_dump(exclude_none=True))
    await svc.session.commit()
    return model
