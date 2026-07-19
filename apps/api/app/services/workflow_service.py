from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.errors import not_found, conflict, bad_request
from app.models.tgbreak import TgbreakProfile
from app.models.workflow import WorkflowProfile, WorkflowStepConfig, STAGES


class WorkflowService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_profile(self, profile_id: str) -> WorkflowProfile:
        stmt = (
            select(WorkflowProfile)
            .where(WorkflowProfile.id == profile_id)
            .options(selectinload(WorkflowProfile.steps))
        )
        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()
        if not profile:
            raise not_found("WORKFLOW_NOT_FOUND", "工作流方案不存在")
        return profile

    async def init_builtin_default(self):
        existing = await self.session.execute(
            select(WorkflowProfile).where(WorkflowProfile.is_default == True)
        )
        if existing.scalars().first():
            return

        from app.models.provider import Provider
        from app.models.prompt import PromptProfile, PromptVersion

        mock_result = await self.session.execute(
            select(Provider).where(Provider.is_builtin == True)
        )
        mock_provider = mock_result.scalars().first()

        prompt_result = await self.session.execute(
            select(PromptProfile)
            .where(PromptProfile.is_builtin == True)
            .options(selectinload(PromptProfile.versions))
        )
        builtin_prompts = {p.stage: p for p in prompt_result.scalars().all()}

        profile = WorkflowProfile(
            name="本地演示",
            description="使用 Mock 服务商的默认工作流",
            is_default=True,
        )
        self.session.add(profile)
        await self.session.flush()

        for stage in STAGES:
            prompt_profile = builtin_prompts.get(stage)
            prompt_version_id = None
            if prompt_profile and prompt_profile.versions:
                prompt_version_id = prompt_profile.versions[-1].id

            model_id = "mock-model" if mock_provider else None
            provider_id = mock_provider.id if mock_provider else None

            step = WorkflowStepConfig(
                workflow_profile_id=profile.id,
                stage=stage,
                provider_id=provider_id,
                model_id=model_id,
                prompt_version_id=prompt_version_id,
            )
            self.session.add(step)

        await self.session.flush()

    async def list_profiles(self) -> list[WorkflowProfile]:
        stmt = (
            select(WorkflowProfile)
            .options(selectinload(WorkflowProfile.steps))
            .order_by(WorkflowProfile.created_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_profile(self, data: dict) -> WorkflowProfile:
        profile = WorkflowProfile(
            name=data["name"],
            description=data.get("description", ""),
        )
        self.session.add(profile)
        await self.session.flush()

        for stage in STAGES:
            step = WorkflowStepConfig(
                workflow_profile_id=profile.id,
                stage=stage,
            )
            self.session.add(step)

        await self.session.flush()
        await self.session.refresh(profile, ["steps"])
        return profile

    async def get_profile(self, profile_id: str) -> WorkflowProfile:
        return await self._get_profile(profile_id)

    async def update_profile(self, profile_id: str, data: dict) -> WorkflowProfile:
        profile = await self._get_profile(profile_id)

        if data.get("name") is not None:
            profile.name = data["name"]
        if data.get("description") is not None:
            profile.description = data["description"]

        await self.session.flush()
        return profile

    async def duplicate_profile(self, profile_id: str) -> WorkflowProfile:
        source = await self._get_profile(profile_id)

        new_profile = WorkflowProfile(
            name=f"{source.name} 副本",
            description=source.description,
            is_default=False,
        )
        self.session.add(new_profile)
        await self.session.flush()

        for src_step in source.steps:
            step = WorkflowStepConfig(
                workflow_profile_id=new_profile.id,
                stage=src_step.stage,
                provider_id=src_step.provider_id,
                model_id=src_step.model_id,
                prompt_version_id=src_step.prompt_version_id,
                writer_prompt_mode=src_step.writer_prompt_mode or "builtin",
                tgbreak_profile_id=src_step.tgbreak_profile_id,
                temperature=src_step.temperature,
                top_p=src_step.top_p,
                max_output_tokens=src_step.max_output_tokens,
                timeout_seconds=src_step.timeout_seconds,
            )
            self.session.add(step)

        await self.session.flush()
        await self.session.refresh(new_profile, ["steps"])
        return new_profile

    async def delete_profile(self, profile_id: str):
        profile = await self._get_profile(profile_id)
        await self.session.delete(profile)
        await self.session.flush()

    async def update_step(self, profile_id: str, stage: str, data: dict) -> WorkflowStepConfig:
        if stage not in STAGES:
            raise bad_request("INVALID_STAGE", f"无效的阶段: {stage}，有效值为 {', '.join(STAGES)}")

        profile = await self._get_profile(profile_id)

        step = None
        for s in profile.steps:
            if s.stage == stage:
                step = s
                break

        if not step:
            raise not_found("STEP_NOT_FOUND", f"未找到 {stage} 阶段的配置")

        if data.get("provider_id") is not None:
            step.provider_id = data["provider_id"] if data["provider_id"] else None
        if data.get("model_id") is not None:
            step.model_id = data["model_id"] if data["model_id"] else None
        if data.get("prompt_version_id") is not None:
            step.prompt_version_id = data["prompt_version_id"] if data["prompt_version_id"] else None
        if data.get("writer_prompt_mode") is not None:
            if stage != "writer":
                raise bad_request(
                    "INVALID_WRITER_PROMPT_MODE",
                    "writer_prompt_mode 只能配置在 writer 阶段",
                )
            step.writer_prompt_mode = data["writer_prompt_mode"]
        if data.get("tgbreak_profile_id") is not None:
            if stage != "writer":
                raise bad_request(
                    "INVALID_WRITER_PROMPT_MODE",
                    "tgbreak_profile_id 只能配置在 writer 阶段",
                )
            if data["tgbreak_profile_id"]:
                exists = await self.session.execute(
                    select(TgbreakProfile.id).where(
                        TgbreakProfile.id == data["tgbreak_profile_id"]
                    )
                )
                if exists.scalar_one_or_none() is None:
                    raise not_found(
                        "TGBREAK_PROFILE_NOT_FOUND",
                        f"TGbreak 配置不存在: {data['tgbreak_profile_id']}",
                    )
            step.tgbreak_profile_id = (
                data["tgbreak_profile_id"] if data["tgbreak_profile_id"] else None
            )
        if data.get("temperature") is not None:
            t = data["temperature"]
            if t < 0.0 or t > 2.0:
                raise bad_request("INVALID_TEMPERATURE", "temperature 必须在 0.0–2.0 之间")
            step.temperature = t
        if data.get("top_p") is not None:
            p = data["top_p"]
            if p < 0.0 or p > 1.0:
                raise bad_request("INVALID_TOP_P", "top_p 必须在 0.0–1.0 之间")
            step.top_p = p
        if data.get("max_output_tokens") is not None:
            mt = data["max_output_tokens"]
            if mt < 256 or mt > 32768:
                raise bad_request("INVALID_MAX_TOKENS", "max_output_tokens 必须在 256–32768 之间")
            step.max_output_tokens = mt
        if data.get("timeout_seconds") is not None:
            ts = data["timeout_seconds"]
            if ts < 10 or ts > 600:
                raise bad_request("INVALID_TIMEOUT", "timeout_seconds 必须在 10–600 之间")
            step.timeout_seconds = ts

        await self.session.flush()
        return step

    async def set_default(self, profile_id: str) -> WorkflowProfile:
        profile = await self._get_profile(profile_id)

        await self.session.execute(
            update(WorkflowProfile).values(is_default=False)
        )

        profile.is_default = True
        await self.session.flush()
        return profile
