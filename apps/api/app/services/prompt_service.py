import json
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.errors import not_found, conflict, bad_request
from app.models.prompt import PromptProfile, PromptVersion, STAGES, OUTPUT_MODES
from app.prompts.defaults import BUILTIN_PROMPTS
from app.prompts.renderer import render, RenderError


class PromptService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_profile(self, profile_id: str) -> PromptProfile:
        stmt = (
            select(PromptProfile)
            .where(PromptProfile.id == profile_id)
            .options(selectinload(PromptProfile.versions))
        )
        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()
        if not profile:
            raise not_found("PROMPT_PROFILE_NOT_FOUND", "提示词方案不存在")
        return profile

    def _get_latest_version(self, profile: PromptProfile) -> PromptVersion | None:
        if not profile.versions:
            return None
        return profile.versions[-1]

    async def init_builtins(self):
        existing = await self.session.execute(
            select(PromptProfile).where(PromptProfile.is_builtin == True)
        )
        if existing.scalars().first():
            return

        for entry in BUILTIN_PROMPTS:
            profile = PromptProfile(
                stage=entry["stage"],
                name=entry["name"],
                description=entry["description"],
                is_builtin=True,
            )
            self.session.add(profile)
            await self.session.flush()

            version = PromptVersion(
                profile_id=profile.id,
                version_number=1,
                system_template=entry["system_template"],
                user_template=entry["user_template"],
                output_mode=entry["output_mode"],
                output_schema_name=entry["output_schema_name"],
            )
            self.session.add(version)

        await self.session.flush()

    async def list_profiles(self, stage: str | None = None):
        stmt = (
            select(PromptProfile)
            .options(selectinload(PromptProfile.versions))
            .order_by(PromptProfile.created_at)
        )
        if stage:
            stmt = stmt.where(PromptProfile.stage == stage)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_profile(self, data: dict) -> PromptProfile:
        stage = data["stage"]
        if stage not in STAGES:
            raise bad_request("INVALID_STAGE", f"无效的阶段: {stage}，有效值为 {', '.join(STAGES)}")

        output_mode = data.get("output_mode", "structured")
        if output_mode not in OUTPUT_MODES:
            raise bad_request("INVALID_OUTPUT_MODE", f"无效的输出模式: {output_mode}")

        profile = PromptProfile(
            stage=stage,
            name=data["name"],
            description=data.get("description", ""),
            is_builtin=False,
        )
        self.session.add(profile)
        await self.session.flush()

        version = PromptVersion(
            profile_id=profile.id,
            version_number=1,
            system_template=data.get("system_template", ""),
            user_template=data.get("user_template", ""),
            output_mode=output_mode,
            output_schema_name=data.get("output_schema_name"),
        )
        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(profile, ["versions"])
        return profile

    async def get_versions(self, profile_id: str) -> list[PromptVersion]:
        profile = await self._get_profile(profile_id)
        return profile.versions

    async def add_version(self, profile_id: str, data: dict) -> PromptVersion:
        profile = await self._get_profile(profile_id)
        latest = self._get_latest_version(profile)
        next_number = (latest.version_number + 1) if latest else 1

        version = PromptVersion(
            profile_id=profile.id,
            version_number=next_number,
            system_template=data.get("system_template", ""),
            user_template=data.get("user_template", ""),
            output_mode=data.get("output_mode", "structured"),
            output_schema_name=data.get("output_schema_name"),
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def duplicate_profile(self, profile_id: str) -> PromptProfile:
        profile = await self._get_profile(profile_id)

        new_profile = PromptProfile(
            stage=profile.stage,
            name=f"{profile.name} 副本",
            description=profile.description,
            is_builtin=False,
        )
        self.session.add(new_profile)
        await self.session.flush()

        latest = self._get_latest_version(profile)
        if latest:
            version = PromptVersion(
                profile_id=new_profile.id,
                version_number=1,
                system_template=latest.system_template,
                user_template=latest.user_template,
                output_mode=latest.output_mode,
                output_schema_name=latest.output_schema_name,
            )
            self.session.add(version)

        await self.session.flush()
        await self.session.refresh(new_profile, ["versions"])
        return new_profile

    async def restore_default(self, profile_id: str) -> PromptProfile:
        profile = await self._get_profile(profile_id)
        if not profile.is_builtin:
            raise bad_request("NOT_BUILTIN", "只有内置提示词可以恢复默认")

        default = None
        for entry in BUILTIN_PROMPTS:
            if entry["stage"] == profile.stage and entry["name"] == profile.name:
                default = entry
                break

        if not default:
            raise not_found("DEFAULT_NOT_FOUND", "未找到对应的默认提示词")

        latest = self._get_latest_version(profile)
        next_number = (latest.version_number + 1) if latest else 1

        version = PromptVersion(
            profile_id=profile.id,
            version_number=next_number,
            system_template=default["system_template"],
            user_template=default["user_template"],
            output_mode=default["output_mode"],
            output_schema_name=default["output_schema_name"],
        )
        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(profile, ["versions"])
        return profile

    async def export_all(self) -> dict:
        profiles = await self.session.execute(
            select(PromptProfile)
            .where(PromptProfile.is_builtin == False)
            .options(selectinload(PromptProfile.versions))
            .order_by(PromptProfile.created_at)
        )
        profiles = profiles.scalars().all()

        result = []
        for p in profiles:
            latest = self._get_latest_version(p)
            result.append({
                "stage": p.stage,
                "name": p.name,
                "description": p.description,
                "system_template": latest.system_template if latest else "",
                "user_template": latest.user_template if latest else "",
                "output_mode": latest.output_mode if latest else "structured",
                "output_schema_name": latest.output_schema_name if latest else None,
            })

        return {"version": "1.0", "profiles": result}

    async def import_profiles(self, data: dict) -> int:
        count = 0
        for entry in data.get("profiles", []):
            profile_data = {
                "stage": entry["stage"],
                "name": entry["name"],
                "description": entry.get("description", ""),
                "system_template": entry.get("system_template", ""),
                "user_template": entry.get("user_template", ""),
                "output_mode": entry.get("output_mode", "structured"),
                "output_schema_name": entry.get("output_schema_name"),
            }
            await self.create_profile(profile_data)
            count += 1
        return count

    async def render_preview(self, system_template: str, user_template: str, variables: dict[str, str]):
        try:
            system_prompt = render(system_template, variables)
            user_prompt = render(user_template, variables)
            return system_prompt, user_prompt
        except RenderError as e:
            raise bad_request("RENDER_ERROR", "; ".join(e.errors))
