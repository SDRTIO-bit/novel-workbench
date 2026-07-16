import hashlib
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.errors import not_found, bad_request
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.prompt import PromptProfile, PromptVersion, STAGES
from app.models.workflow import WorkflowProfile, WorkflowStepConfig
from app.prompts.renderer import render, validate_variables, RenderError
from app.schemas.context import ContextSource, ContextPreviewRequest

MAX_CONTEXT_CHARS = 128000


class ContextService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def assemble(self, req: ContextPreviewRequest) -> dict:
        project = await self._get_project(req.project_id)

        docs_map = {d.kind: d for d in project.documents}
        chapter = None
        if req.chapter_id:
            chapter = await self._get_chapter(req.chapter_id)

        recent_chapters_raw = await self._fetch_recent_chapters(
            req.project_id, req.chapter_id, count=3
        )

        variables = {}
        variables["project_name"] = project.name
        variables["project_genre"] = project.genre
        variables["author_note"] = project.author_note
        variables["default_pov"] = project.default_pov
        variables["scene_instruction"] = req.scene_instruction
        variables["run_override"] = req.run_override

        if chapter:
            variables["chapter_title"] = chapter.title
            variables["chapter_text"] = self._numbered_text(chapter.current_text)

        if recent_chapters_raw:
            variables["recent_chapters"] = self._format_recent_chapters(recent_chapters_raw)
        else:
            variables["recent_chapters"] = ""

        variables["project_documents"] = self._format_documents(docs_map)

        if req.scene_plan is not None:
            variables["scene_plan"] = json.dumps(req.scene_plan, ensure_ascii=False, indent=2)

        variables["draft_text"] = req.draft_text
        variables["numbered_draft"] = self._numbered_text(req.draft_text) if req.draft_text else ""

        if req.critic_report is not None:
            variables["critic_report"] = json.dumps(req.critic_report, ensure_ascii=False, indent=2)

        if req.selected_issues:
            variables["selected_issues"] = json.dumps(req.selected_issues, ensure_ascii=False, indent=2)
        else:
            variables["selected_issues"] = ""

        variables["revised_text"] = req.revised_text

        variables["chapter_function"] = req.chapter_function or ""
        variables["arc_phase"] = req.arc_phase or ""
        variables["reader_comes_for"] = req.reader_comes_for or ""
        variables["must_deliver"] = req.must_deliver or ""
        variables["must_not_deliver"] = req.must_not_deliver or ""
        variables["main_change"] = req.main_change or ""
        variables["main_payoff"] = req.main_payoff or ""
        variables["ending_hook"] = req.ending_hook or ""
        variables["hook_type"] = req.hook_type or ""
        variables["fuel_reserved_for_later"] = req.fuel_reserved_for_later or ""
        variables["target_length"] = str(req.target_length) if req.target_length else ""

        variables["write_mode"] = req.write_mode or "new_chapter"

        if req.continuation_anchor:
            variables["continuation_anchor"] = req.continuation_anchor
        elif chapter and chapter.current_text:
            anchor = chapter.current_text.strip()
            if len(anchor) > 500:
                anchor = anchor[-500:]
            variables["continuation_anchor"] = anchor
        else:
            variables["continuation_anchor"] = ""

        if req.current_chapter_text:
            variables["current_chapter_text"] = req.current_chapter_text
        elif chapter and chapter.current_text:
            variables["current_chapter_text"] = chapter.current_text.strip()
        else:
            variables["current_chapter_text"] = ""

        untouchable = {"scene_instruction", "run_override", "draft_text", "numbered_draft",
                       "revised_text", "scene_plan", "critic_report", "selected_issues",
                       "continuation_anchor", "current_chapter_text"}

        truncated = False
        sources: list[ContextSource] = []

        for key in variables:
            value = variables[key] or ""
            char_count = len(value)
            sources.append(ContextSource(name=key, char_count=char_count, truncated=False))

        total = sum(s.char_count for s in sources)
        limit = MAX_CONTEXT_CHARS

        if total > limit:
            truncated = True
            gap = total - limit

            gap = self._truncate_source(sources, "recent_chapters", gap)

            if gap > 0:
                gap = self._truncate_source(sources, "project_documents", gap)

            if gap > 0:
                raise bad_request(
                    "CONTEXT_TOO_LARGE",
                    f"上下文过大: 核心变量占用 {total - limit} 字符超出上限 {limit}, 请精简项目资料"
                )

            source_map = {s.name: s for s in sources}
            for key in untouchable:
                if key in source_map:
                    continue
            for name in ["recent_chapters", "project_documents"]:
                if name in source_map:
                    variables[name] = variables[name][:source_map[name].char_count]

            total = sum(s.char_count for s in sources)

        snapshot_hash = self._compute_hash(variables)

        system_template, user_template = await self._resolve_prompt(
            stage=req.stage,
            workflow_profile_id=req.workflow_profile_id,
            prompt_version_id=req.prompt_version_id,
        )

        try:
            system_prompt = render(system_template, variables, strict=True)
            user_prompt = render(user_template, variables, strict=True)
        except RenderError as e:
            raise bad_request("RENDER_ERROR", "; ".join(e.errors))

        return {
            "sources": sources,
            "rendered_system_prompt": system_prompt,
            "rendered_user_prompt": user_prompt,
            "input_snapshot_hash": snapshot_hash,
            "total_chars": total,
            "truncated": truncated,
        }

    def _truncate_source(self, sources: list[ContextSource], name: str, gap: int) -> int:
        for s in sources:
            if s.name == name:
                cut = min(s.char_count, gap)
                s.char_count -= cut
                s.truncated = True
                return gap - cut
        return gap

    async def _get_project(self, project_id: str) -> Project:
        stmt = (
            select(Project)
            .where(Project.id == project_id, Project.deleted_at.is_(None))
            .options(selectinload(Project.documents))
        )
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            raise not_found("PROJECT_NOT_FOUND", "小说项目不存在")
        return project

    async def _get_chapter(self, chapter_id: str) -> Chapter:
        stmt = select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise not_found("CHAPTER_NOT_FOUND", "章节不存在")
        return chapter

    async def _fetch_recent_chapters(
        self, project_id: str, exclude_chapter_id: str | None, count: int
    ) -> list[Chapter]:
        stmt = (
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.deleted_at.is_(None),
            )
            .order_by(Chapter.sort_order)
        )
        result = await self.session.execute(stmt)
        chapters = list(result.scalars().all())

        if exclude_chapter_id:
            chapters = [c for c in chapters if c.id != exclude_chapter_id]

        return chapters[-count:]

    def _format_documents(self, docs_map: dict[str, "ProjectDocument"]) -> str:
        lines = []
        for kind in ["synopsis", "outline", "characters", "world", "style", "principles", "summary", "notes"]:
            doc = docs_map.get(kind)
            if doc and doc.content.strip():
                lines.append(f"## {doc.title or kind.capitalize()}\n{doc.content.strip()}")
        return "\n\n".join(lines)

    def _format_recent_chapters(self, chapters: list[Chapter]) -> str:
        parts = []
        for ch in chapters:
            header = f"第{ch.sort_order}章 {ch.title}".strip()
            body = ch.current_text.strip()
            if body:
                parts.append(f"### {header}\n{body}")
        return "\n\n".join(parts)

    def _numbered_text(self, text: str) -> str:
        paragraphs = text.strip().split("\n\n")
        return "\n\n".join(
            f"[P{i + 1:03d}] {p}" for i, p in enumerate(paragraphs)
        )

    def _compute_hash(self, variables: dict[str, str]) -> str:
        ordered = dict(sorted(variables.items()))
        raw = json.dumps(ordered, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _resolve_prompt(
        self,
        stage: str,
        workflow_profile_id: str | None,
        prompt_version_id: str | None,
    ) -> tuple[str, str]:
        if prompt_version_id:
            stmt = select(PromptVersion).where(PromptVersion.id == prompt_version_id)
            res = await self.session.execute(stmt)
            version = res.scalar_one_or_none()
            if not version:
                raise not_found("PROMPT_VERSION_NOT_FOUND", "提示词版本不存在")
            return version.system_template, version.user_template

        if workflow_profile_id:
            return await self._resolve_from_workflow(workflow_profile_id, stage)

        default_workflow = await self._get_default_workflow()
        if default_workflow:
            return await self._resolve_from_workflow(default_workflow.id, stage)

        builtin = await self._get_builtin_prompt(stage)
        if builtin:
            return builtin.system_template, builtin.user_template

        raise bad_request("PROMPT_NOT_FOUND", f"阶段 {stage} 没有可用的提示词")

    async def _resolve_from_workflow(self, workflow_id: str, stage: str) -> tuple[str, str]:
        stmt = (
            select(WorkflowProfile)
            .where(WorkflowProfile.id == workflow_id)
            .options(selectinload(WorkflowProfile.steps))
        )
        result = await self.session.execute(stmt)
        wf = result.scalar_one_or_none()
        if not wf:
            raise not_found("WORKFLOW_NOT_FOUND", "工作流方案不存在")

        step = next((s for s in wf.steps if s.stage == stage), None)
        if step and step.prompt_version_id:
            pv_stmt = select(PromptVersion).where(PromptVersion.id == step.prompt_version_id)
            pv_res = await self.session.execute(pv_stmt)
            pv = pv_res.scalar_one_or_none()
            if pv:
                return pv.system_template, pv.user_template

        builtin = await self._get_builtin_prompt(stage)
        if builtin:
            return builtin.system_template, builtin.user_template

        raise bad_request("PROMPT_NOT_FOUND", f"阶段 {stage} 没有可用的提示词")

    async def _get_default_workflow(self) -> WorkflowProfile | None:
        stmt = (
            select(WorkflowProfile)
            .where(WorkflowProfile.is_default == True)
            .options(selectinload(WorkflowProfile.steps))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_builtin_prompt(self, stage: str) -> PromptVersion | None:
        stmt = (
            select(PromptProfile)
            .where(PromptProfile.stage == stage, PromptProfile.is_builtin == True)
            .options(selectinload(PromptProfile.versions))
        )
        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()
        if profile and profile.versions:
            return profile.versions[-1]
        return None
