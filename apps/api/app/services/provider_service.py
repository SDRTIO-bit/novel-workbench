import json
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.errors import not_found, conflict, bad_request
from app.models.provider import Provider, ProviderModel, PROVIDER_TYPES
from app.services.secret_service import encrypt_api_key, decrypt_api_key

DEFAULT_MOCK_MODELS = ["mock-model"]


class ProviderService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_provider(self, provider_id: str) -> Provider:
        stmt = (
            select(Provider)
            .where(Provider.id == provider_id)
            .options(selectinload(Provider.models))
        )
        result = await self.session.execute(stmt)
        provider = result.scalar_one_or_none()
        if not provider:
            raise not_found("PROVIDER_NOT_FOUND", "服务商不存在")
        return provider

    async def init_builtins(self):
        existing = await self.session.execute(
            select(Provider).where(Provider.is_builtin == True)
        )
        if existing.scalars().first():
            return

        provider = Provider(
            name="本地演示",
            provider_type="mock",
            base_url="",
            is_builtin=True,
        )
        self.session.add(provider)
        await self.session.flush()

        for model_id in DEFAULT_MOCK_MODELS:
            model = ProviderModel(
                provider_id=provider.id,
                model_id=model_id,
                display_name=model_id,
            )
            self.session.add(model)

        await self.session.flush()

    async def list_providers(self) -> list[Provider]:
        stmt = (
            select(Provider)
            .options(selectinload(Provider.models))
            .order_by(Provider.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_provider(self, data: dict) -> Provider:
        provider_type = data.get("provider_type", "openai_compatible")
        if provider_type not in PROVIDER_TYPES:
            raise bad_request("INVALID_PROVIDER_TYPE", f"无效的服务商类型: {provider_type}")

        api_key = data.get("api_key", "")
        encrypted = encrypt_api_key(api_key) if api_key else None

        provider = Provider(
            name=data["name"],
            provider_type=provider_type,
            base_url=data.get("base_url", ""),
            encrypted_api_key=encrypted,
            extra_headers_json=data.get("extra_headers_json", "{}"),
            enabled=data.get("enabled", True),
        )
        self.session.add(provider)
        await self.session.flush()
        await self.session.refresh(provider, ["models"])
        return provider

    async def update_provider(self, provider_id: str, data: dict) -> Provider:
        provider = await self._get_provider(provider_id)

        if data.get("name") is not None:
            provider.name = data["name"]
        if data.get("base_url") is not None:
            provider.base_url = data["base_url"]
        if data.get("provider_type") is not None:
            if data["provider_type"] not in PROVIDER_TYPES:
                raise bad_request("INVALID_PROVIDER_TYPE", "无效的服务商类型")
            provider.provider_type = data["provider_type"]
        if data.get("extra_headers_json") is not None:
            provider.extra_headers_json = data["extra_headers_json"]
        if data.get("enabled") is not None:
            provider.enabled = data["enabled"]

        if data.get("clear_api_key"):
            provider.encrypted_api_key = None
        elif data.get("api_key") is not None and data["api_key"]:
            provider.encrypted_api_key = encrypt_api_key(data["api_key"])

        await self.session.flush()
        await self.session.refresh(provider, ["models"])
        return provider

    async def delete_provider(self, provider_id: str):
        provider = await self._get_provider(provider_id)

        if provider.is_builtin:
            raise bad_request("BUILTIN_PROVIDER", "内置服务商不允许删除")

        await self.session.delete(provider)
        await self.session.flush()

    async def test_connection(self, provider_id: str) -> dict:
        provider = await self._get_provider(provider_id)

        if provider.provider_type == "mock":
            return {"success": True, "message": "Mock 服务商无需测试"}

        api_key = decrypt_api_key(provider.encrypted_api_key)
        if not api_key:
            return {"success": False, "message": "未设置 API Key"}

        if not provider.base_url:
            return {"success": False, "message": "未设置 Base URL"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Authorization": f"Bearer {api_key}"}
                if provider.extra_headers_json:
                    try:
                        extra = json.loads(provider.extra_headers_json)
                        headers.update(extra)
                    except json.JSONDecodeError:
                        pass

                url = provider.base_url.rstrip("/") + "/models"
                resp = await client.get(url, headers=headers)

                if resp.status_code == 200:
                    return {"success": True, "message": "连接成功"}
                if resp.status_code == 401:
                    return {"success": False, "message": "认证失败 (401)"}
                if resp.status_code == 403:
                    return {"success": False, "message": "权限不足 (403)"}
                return {"success": False, "message": f"HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            return {"success": False, "message": "连接超时"}
        except httpx.ConnectError:
            return {"success": False, "message": "连接失败，请检查 Base URL"}
        except Exception as e:
            return {"success": False, "message": f"连接异常: {str(e)}"}

    async def sync_models(self, provider_id: str) -> dict:
        provider = await self._get_provider(provider_id)

        if provider.provider_type == "mock":
            return {"models": provider.models, "added": 0, "removed": 0}

        api_key = decrypt_api_key(provider.encrypted_api_key)
        if not api_key:
            raise bad_request("NO_API_KEY", "未设置 API Key，无法同步模型列表")

        if not provider.base_url:
            raise bad_request("NO_BASE_URL", "未设置 Base URL")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Authorization": f"Bearer {api_key}"}
                if provider.extra_headers_json:
                    try:
                        extra = json.loads(provider.extra_headers_json)
                        headers.update(extra)
                    except json.JSONDecodeError:
                        pass

                url = provider.base_url.rstrip("/") + "/models"
                resp = await client.get(url, headers=headers)

                if resp.status_code != 200:
                    raise bad_request(
                        "SYNC_FAILED",
                        f"获取模型列表失败 (HTTP {resp.status_code})",
                    )

                data = resp.json()
                remote_models = data.get("data", [])
                remote_ids = {m["id"] for m in remote_models if "id" in m}

                existing_models = [m for m in provider.models if not m.is_manual]
                existing_ids = {m.model_id for m in existing_models}

                to_add = remote_ids - existing_ids
                to_remove = existing_ids - remote_ids

                added = 0
                for mid in to_add:
                    remote = next((m for m in remote_models if m.get("id") == mid), {})
                    model = ProviderModel(
                        provider_id=provider.id,
                        model_id=mid,
                        display_name=remote.get("id", mid),
                    )
                    self.session.add(model)
                    added += 1

                for model in existing_models:
                    if model.model_id in to_remove:
                        await self.session.delete(model)

                await self.session.flush()
                await self.session.refresh(provider, ["models"])

                return {
                    "models": provider.models,
                    "added": added,
                    "removed": len(to_remove),
                }

        except httpx.TimeoutException:
            raise bad_request("SYNC_TIMEOUT", "同步超时")
        except httpx.ConnectError:
            raise bad_request("SYNC_FAILED", "连接失败，请检查 Base URL")

    async def add_model(self, provider_id: str, data: dict) -> ProviderModel:
        provider = await self._get_provider(provider_id)

        for m in provider.models:
            if m.model_id == data["model_id"]:
                raise conflict("MODEL_EXISTS", f"模型 {data['model_id']} 已存在")

        model = ProviderModel(
            provider_id=provider.id,
            model_id=data["model_id"],
            display_name=data.get("display_name", data["model_id"]),
            is_manual=True,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def update_model(self, provider_id: str, model_id_str: str, data: dict) -> ProviderModel:
        provider = await self._get_provider(provider_id)

        model = None
        for m in provider.models:
            if m.id == model_id_str:
                model = m
                break

        if not model:
            raise not_found("MODEL_NOT_FOUND", "模型不存在")

        if data.get("display_name") is not None:
            model.display_name = data["display_name"]
        if data.get("enabled") is not None:
            model.enabled = data["enabled"]

        await self.session.flush()
        return model
