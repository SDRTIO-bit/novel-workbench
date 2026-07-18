import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.generation import GenerationRun, GenerationStep, GenerationCandidate
from app.models.workflow import WorkflowProfile, WorkflowStepConfig
from app.models.prompt import PromptVersion
from app.errors import not_found, conflict, bad_request


class GenerationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self, project_id: str, chapter_id: str | None,
        workflow_profile_id: str | None, scene_instruction: str,
    ) -> GenerationRun:
        run = GenerationRun(
            project_id=project_id,
            chapter_id=chapter_id,
            workflow_profile_id=workflow_profile_id,
            scene_instruction=scene_instruction,
            status="pending",
        )
        self.session.add(run)
        await self.session.flush()

        stages = ["planner", "writer", "critic", "reviser", "judge"]
        for stage in stages:
            step = GenerationStep(
                run_id=run.id,
                stage=stage,
                status="pending",
            )
            self.session.add(step)

        await self.session.flush()

        stmt = (
            select(GenerationRun)
            .where(GenerationRun.id == run.id)
            .options(
                selectinload(GenerationRun.steps)
                .selectinload(GenerationStep.candidates)
            )
        )
        result = await self.session.execute(stmt)
        run = result.scalar_one()
        run.steps.sort(key=lambda s: ["planner", "writer", "critic", "reviser", "judge"].index(s.stage))
        return run

    async def get_run(self, run_id: str) -> GenerationRun | None:
        stmt = (
            select(GenerationRun)
            .where(GenerationRun.id == run_id)
            .options(
                selectinload(GenerationRun.steps)
                .selectinload(GenerationStep.candidates)
            )
        )
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            run.steps.sort(key=lambda s: ["planner", "writer", "critic", "reviser", "judge"].index(s.stage))
        return run

    async def get_run_or_404(self, run_id: str) -> GenerationRun:
        run = await self.get_run(run_id)
        if not run:
            raise not_found("RUN_NOT_FOUND", "运行记录不存在")
        return run

    async def list_runs_by_project(self, project_id: str) -> list[GenerationRun]:
        stmt = (
            select(GenerationRun)
            .where(GenerationRun.project_id == project_id)
            .options(
                selectinload(GenerationRun.steps)
                .selectinload(GenerationStep.candidates)
            )
            .order_by(GenerationRun.created_at.desc())
        )
        result = await self.session.execute(stmt)
        runs = list(result.scalars().all())
        stage_order = ["planner", "writer", "critic", "reviser", "judge"]
        for run in runs:
            run.steps.sort(key=lambda s: stage_order.index(s.stage))
        return runs

    async def get_step(self, run_id: str, stage: str) -> GenerationStep | None:
        stmt = (
            select(GenerationStep)
            .where(GenerationStep.run_id == run_id, GenerationStep.stage == stage)
            .options(selectinload(GenerationStep.candidates))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_step_or_404(self, run_id: str, stage: str) -> GenerationStep:
        step = await self.get_step(run_id, stage)
        if not step:
            raise not_found("STEP_NOT_FOUND", f"步骤 {stage} 不存在")
        return step

    async def create_candidate(
        self,
        step_id: str,
        attempt_number: int,
        provider_id: str | None,
        model_id: str | None,
        prompt_version_id: str | None,
        parameters_json: str,
        run_override: str,
        rendered_system_prompt: str,
        rendered_user_prompt: str,
        raw_response: str,
        parsed_output_json: str | None,
        text_output: str,
        error_code: str | None,
        error_message: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int | None,
        finish_reason: str | None,
        reasoning_tokens: int | None,
    ) -> GenerationCandidate:
        candidate = GenerationCandidate(
            step_id=step_id,
            attempt_number=attempt_number,
            provider_id=provider_id,
            model_id=model_id,
            prompt_version_id=prompt_version_id,
            parameters_json=parameters_json,
            run_override=run_override,
            rendered_system_prompt=rendered_system_prompt,
            rendered_user_prompt=rendered_user_prompt,
            raw_response=raw_response,
            parsed_output_json=parsed_output_json,
            text_output=text_output,
            error_code=error_code,
            error_message=error_message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            reasoning_tokens=reasoning_tokens,
        )
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def get_workflow_step_config(
        self, workflow_id: str, stage: str
    ) -> WorkflowStepConfig | None:
        stmt = (
            select(WorkflowStepConfig)
            .where(
                WorkflowStepConfig.workflow_profile_id == workflow_id,
                WorkflowStepConfig.stage == stage,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_workflow(self) -> WorkflowProfile | None:
        stmt = (
            select(WorkflowProfile)
            .where(WorkflowProfile.is_default == True)
            .options(selectinload(WorkflowProfile.steps))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_prompt_version(self, version_id: str) -> PromptVersion | None:
        stmt = select(PromptVersion).where(PromptVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_step_status(self, step: GenerationStep, status: str):
        step.status = status
        await self.session.flush()

    async def select_candidate(self, step: GenerationStep, candidate_id: str):
        step.selected_candidate_id = candidate_id
        step.status = "completed"
        for c in step.candidates:
            c.is_selected = (c.id == candidate_id)
        await self.session.flush()

    async def mark_downstream_stale(self, run: GenerationRun, from_stage: str):
        stages = ["planner", "writer", "critic", "reviser", "judge"]
        try:
            idx = stages.index(from_stage)
        except ValueError:
            return
        for stage in stages[idx + 1:]:
            step = await self.get_step(run.id, stage)
            if step and step.status not in ("pending",):
                step.status = "stale"
                step.selected_candidate_id = None
        await self.session.flush()
