"""Run the frozen generalization batch once and export external-review evidence.

The script deliberately never updates prompt versions, workflow settings, or
existing candidates.  It creates three new minimal projects/runs, invokes each
stage at most once, and writes review packages beneath ``__evaluation``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(API_ROOT))

from app.models.generation import GenerationCandidate, GenerationRun, GenerationStep
from app.models.prompt import PromptVersion
from app.models.provider import Provider
from app.models.workflow import WorkflowProfile, WorkflowStepConfig
from app.schemas.chapter import ChapterCreate
from app.schemas.project import DocumentUpdate, ProjectCreate
from app.services.chapter_service import ChapterService
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from tools.novel_eval_mcp.export import blind_mapping, build_blind_pair, write_json


SEED = 20260719
STAGES = ("planner", "writer", "critic", "reviser", "judge")
CASE_SPECS = {
    "CASE-002": {
        "title": "校园尴尬",
        "scene_brief": "班长在公开点名前发现同学校服扣错；不能当众说明，必须用具体动作让对方自己发现。",
        "scene_instruction": """校园晨会即将公开点名。班长林澈在队伍前发现同学周宁把校服扣错，最上面的扣眼错了一格。周宁正要走向点名台，周围同学都在看。林澈不能当众说明或嘲笑，必须只依据眼前信息，用一个具体动作让周宁自己发现。写人物如何判断、放弃直接提醒、作出选择并承担时间或位置上的代价；让后果可见，停在新的可见事实，不替读者解释关系。""",
    },
    "CASE-003": {
        "title": "信息误判",
        "scene_brief": "人物只听到半段电话，误以为朋友要离开，并作出带来具体麻烦的选择。",
        "scene_instruction": """傍晚，许遥在走廊只听见朋友顾言电话的后半句：'……明天一早就走，钥匙我会放在门卫。'她没有听到前半句，误以为顾言要搬走。她必须依据这点有限信息判断，放弃当面追问，做出一个会造成可见麻烦的具体选择。写选择、代价和即时后果；结尾停在新事实成立的位置，不解释顾言真正要去哪里。""",
    },
    "CASE-004": {
        "title": "失败选择",
        "scene_brief": "人物为逃避小责任隐瞒事实，另一个人已承担后果；结尾停在无法立刻撤回的可见事实。",
        "scene_instruction": """放学后，值日生赵朔不小心把实验室借用登记表夹进自己的书包。他担心承认会被老师留下，于是看见同组的陈可被问起登记表时选择沉默。赵朔必须只依据现场信息作出这个失败选择，写出他放弃承认、隐瞒的具体动作，以及陈可因此承担的可见后果。场景停在错误已经造成但还没解决的可见事实；不准用暖灯、猫或总结性安慰收场。""",
    },
}


def _json(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _candidate_record(candidate: GenerationCandidate | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "provider_id": candidate.provider_id,
        "model_id": candidate.model_id,
        "prompt_version_id": candidate.prompt_version_id,
        "parameters": _json(candidate.parameters_json),
        "raw_response": candidate.raw_response,
        "model_parsed_output": _json(candidate.model_parsed_output_json),
        "parsed_output": _json(candidate.parsed_output_json),
        "text_output": candidate.text_output,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "reasoning_tokens": candidate.reasoning_tokens,
        "latency_ms": candidate.latency_ms,
        "finish_reason": candidate.finish_reason,
        "error_code": candidate.error_code,
        "error_message": candidate.error_message,
        "is_selected": candidate.is_selected,
    }


async def _workflow_snapshot(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(WorkflowProfile)
        .where(WorkflowProfile.is_default.is_(True))
        .options(selectinload(WorkflowProfile.steps))
    )
    workflow = result.scalar_one()
    provider_rows = (await session.execute(select(Provider))).scalars().all()
    providers = {provider.id: provider for provider in provider_rows}
    steps: dict[str, Any] = {}
    for step in workflow.steps:
        version = await session.get(PromptVersion, step.prompt_version_id)
        provider = providers.get(step.provider_id)
        steps[step.stage] = {
            "prompt_version_id": step.prompt_version_id,
            "prompt_version_number": version.version_number if version else None,
            "output_schema_name": version.output_schema_name if version else None,
            "provider": {
                "id": step.provider_id,
                "name": provider.name if provider else None,
                "type": provider.provider_type if provider else None,
                "base_url": provider.base_url if provider else None,
            },
            "model_id": step.model_id,
            "temperature": step.temperature,
            "top_p": step.top_p,
            "max_output_tokens": step.max_output_tokens,
            "timeout_seconds": step.timeout_seconds,
            "writer_prompt_mode": step.writer_prompt_mode,
        }
    revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    return {"workflow_id": workflow.id, "workflow_name": workflow.name, "steps": steps, "alembic_revision": revision}


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


async def _ensure_baseline(session: AsyncSession, root: Path) -> dict[str, Any]:
    snapshot = await _workflow_snapshot(session)
    manifest = {
        "batch": "GENERALIZATION_BATCH_V1",
        "random_seed": SEED,
        "git_commit": _git_commit(),
        "alembic_revision": snapshot.pop("alembic_revision"),
        "workflow": snapshot,
        "frozen_stages": list(STAGES),
        "rule": "PromptVersion, provider/model, and workflow settings are read-only for this batch.",
    }
    path = root / "baseline_manifest.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable = {key: existing.get(key) for key in ("workflow", "alembic_revision")}
        expected = {key: manifest.get(key) for key in ("workflow", "alembic_revision")}
        if comparable != expected:
            raise RuntimeError("frozen baseline differs from current database; refusing to run")
        return existing
    write_json(path, manifest)
    return manifest


async def _load_run(session: AsyncSession, run_id: str) -> GenerationRun:
    # A stage failure can create its candidate after the run was initially
    # loaded.  Expire prior relationship collections before exporting evidence.
    session.expire_all()
    result = await session.execute(
        select(GenerationRun)
        .where(GenerationRun.id == run_id)
        .options(selectinload(GenerationRun.steps).selectinload(GenerationStep.candidates))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def _selected(run: GenerationRun, stage: str) -> GenerationCandidate | None:
    step = next(item for item in run.steps if item.stage == stage)
    return next((candidate for candidate in step.candidates if candidate.id == step.selected_candidate_id), None)


async def _run_case(session: AsyncSession, root: Path, case_id: str, spec: dict[str, str], baseline: dict[str, Any]) -> dict[str, Any]:
    project_service = ProjectService(session)
    chapter_service = ChapterService(session)
    generation = GenerationService(session)
    project = await project_service.create_project(ProjectCreate(name=f"Generalization {case_id}", genre="现实场景"))
    await project_service.update_document(project.id, "principles", DocumentUpdate(
        title="冻结评估约束", content="仅执行既有 Planner→Writer→Critic→Reviser→Judge 管线；不得以案例改变提示词。"
    ))
    chapter = await chapter_service.create_chapter(project.id, ChapterCreate(title=spec["title"], sort_order=1))
    workflow_id = baseline["workflow"]["workflow_id"]
    run = await generation.create_run(project.id, chapter.id, workflow_id, spec["scene_instruction"])
    await session.commit()

    error: dict[str, str] | None = None
    for stage in STAGES:
        frozen = baseline["workflow"]["steps"][stage]
        override = {
            "provider_id": frozen["provider"]["id"], "model_id": frozen["model_id"],
            "prompt_version_id": frozen["prompt_version_id"], "temperature": frozen["temperature"],
            "top_p": frozen["top_p"], "max_output_tokens": frozen["max_output_tokens"],
            "timeout_seconds": frozen["timeout_seconds"],
        }
        try:
            candidate = await generation.execute_stage(run.id, stage, override)
            await session.flush()
            if candidate.error_code:
                error = {"stage": stage, "code": candidate.error_code, "message": candidate.error_message or ""}
                await session.commit()
                break
            await generation.select_candidate(run.id, stage, candidate.id)
            if stage == "critic":
                parsed = _json(candidate.parsed_output_json) or {}
                issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
                issue_ids = [str(issue["issue_id"]) for issue in issues if issue.get("issue_id")]
                if issue_ids:
                    operations = {str(issue["issue_id"]): issue.get("recommended_operation") for issue in issues if issue.get("issue_id")}
                    await generation.select_critic_issues(run.id, issue_ids, operations)
            await session.commit()
        except Exception as exc:  # infrastructure failures are recorded and terminate this case
            await session.rollback()
            error = {"stage": stage, "code": type(exc).__name__, "message": str(exc)}
            break

    run = await _load_run(session, run.id)
    return await _export_case(root, case_id, spec["scene_brief"], run, error)


async def _export_case(root: Path, case_id: str, scene_brief: str, run: GenerationRun, error: dict[str, str] | None) -> dict[str, Any]:
    writer = _selected(run, "writer")
    planner = _selected(run, "planner")
    critic = _selected(run, "critic")
    reviser = _selected(run, "reviser")
    judge = _selected(run, "judge")
    judge_data = _json(judge.parsed_output_json) if judge else {}
    writer_text = (writer.text_output or writer.raw_response) if writer else ""
    reviser_text = (reviser.text_output or reviser.raw_response) if reviser else ""
    if isinstance(judge_data, dict) and judge_data.get("final_text"):
        final_text, final_source = judge_data["final_text"], "judge_final_text"
    elif isinstance(judge_data, dict) and judge_data.get("decision") == "accept_original":
        final_text, final_source = writer_text, "writer"
    else:
        final_text, final_source = reviser_text or writer_text, "reviser" if reviser_text else "writer"
    case_dir = root / "cases" / case_id
    source_mapping = {
        "final_composition_source": final_source,
        "writer_candidate_id": writer.id if writer else None,
        "reviser_candidate_id": reviser.id if reviser else None,
        "judge_candidate_id": judge.id if judge else None,
        "judge_decision": judge_data.get("decision") if isinstance(judge_data, dict) else None,
    }
    write_json(case_dir / "blind_pair.json", build_blind_pair(
        case_id=case_id, scene_brief=scene_brief, writer_text=writer_text, final_text=final_text, seed=SEED
    ))
    write_json(case_dir / "planner_contract.json", {
        "case_id": case_id, "planner_candidate_id": planner.id if planner else None,
        "planner_contract": _json(planner.parsed_output_json) if planner else None,
    })
    stage_records = {}
    for step in run.steps:
        stage_records[step.stage] = {
            "status": step.status, "selected_candidate_id": step.selected_candidate_id,
            "selected_issue_ids": _json(step.selected_issue_ids_json),
            "candidates": [_candidate_record(candidate) for candidate in step.candidates],
        }
    write_json(case_dir / "pipeline_evidence.json", {
        "case_id": case_id, "run_id": run.id, "run_status": run.status, "stages": stage_records,
        "final_composition": final_text, "source_mapping": source_mapping, "error": error,
    })
    write_json(case_dir / "source_mapping.private.json", {
        "blind_mapping": blind_mapping(
            case_id=case_id,
            writer_candidate_id=writer.id if writer else None,
            final_source=final_source,
            seed=SEED,
        ),
        "source_mapping": source_mapping,
    })
    (case_dir / "final_composition.txt").write_text(final_text, encoding="utf-8")
    return {"case_id": case_id, "status": "failed" if error else "completed", "run_id": run.id, "error": error}


async def _export_case_001(session: AsyncSession, root: Path) -> dict[str, Any]:
    writer_id = "ee2c90be-a734-4a76-a119-92a5139f470e"
    result = await session.execute(
        select(GenerationCandidate)
        .where(GenerationCandidate.id == writer_id)
        .options(selectinload(GenerationCandidate.step).selectinload(GenerationStep.run).selectinload(GenerationRun.steps).selectinload(GenerationStep.candidates))
    )
    writer = result.scalar_one()
    run = writer.step.run
    record = await _export_case(root, "CASE-001", "黄昏书屋：老陈以沉默给门口的小满留下进入空间。", run, None)
    case_dir = root / "cases" / "CASE-001"
    writer_text = writer.text_output or writer.raw_response
    final_text = (REPO_ROOT / "__final" / "final_composition.txt").read_text(encoding="utf-8")
    final_mapping = json.loads((REPO_ROOT / "__final" / "source_mapping.json").read_text(encoding="utf-8"))
    write_json(case_dir / "blind_pair.json", build_blind_pair(
        case_id="CASE-001", scene_brief="黄昏书屋：老陈以沉默给门口的小满留下进入空间。",
        writer_text=writer_text, final_text=final_text, seed=SEED,
    ))
    evidence = json.loads((case_dir / "pipeline_evidence.json").read_text(encoding="utf-8"))
    evidence["final_composition"] = final_text
    evidence["source_mapping"] = final_mapping
    write_json(case_dir / "pipeline_evidence.json", evidence)
    write_json(case_dir / "source_mapping.private.json", {
        "blind_mapping": blind_mapping(
            case_id="CASE-001", writer_candidate_id=writer.id,
            final_source="final_composition", seed=SEED,
        ),
        "source_mapping": final_mapping,
    })
    (case_dir / "final_composition.txt").write_text(final_text, encoding="utf-8")
    return record


def _write_prompt(root: Path) -> None:
    (root / "GPT_EVALUATOR_PROMPT.md").write_text("""# Novel Workbench 外部评估员

你是独立外部评估员，不参与正文生成、候选选择或 Prompt 设计。

逐个处理全部 case，严格执行：

1. 调用 `get_blind_pair(case_id)`，仅作匿名读者盲评；先保存初始判断，不能读取来源或 Planner。
2. 调用 `get_planner_contract(case_id)`，按 visible_trigger、rejected_alternative、character_choice、cost_or_commitment、immediate_consequence、next_constraint、stop_state、must_not_append 审计 A/B；每项只能是 present、partial、missing、contradicted。
3. 调用 `get_pipeline_evidence(case_id)`，检查 Critic、Reviser、Judge 和最终合成；不要改写正文。
4. 调用 `save_evaluation_result(case_id, result)` 立即保存结构化结果，再处理下一个 case。
5. 全部结束后调用 `get_evaluation_summary`。

不要因文字更长、更华丽或形容词更多而偏好。重点观察人物是否在有限信息下处理具体麻烦、作出可替代选择、承担可见后果，并停在新事实。所有判断必须引用具体句子或段落。不得改写正文、提出新 Prompt 或新架构。
""", encoding="utf-8")


def _write_report(root: Path, cases: list[dict[str, Any]]) -> None:
    rows = "\n".join(f"| {case['case_id']} | {case['status']} | {case.get('run_id', '—')} |" for case in cases)
    metrics_rows = []
    for case in cases:
        evidence_path = root / "cases" / case["case_id"] / "pipeline_evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        candidates = [
            candidate for stage in evidence["stages"].values()
            for candidate in stage["candidates"]
        ]
        metrics_rows.append(
            "| {case_id} | {input_tokens} | {output_tokens} | {latency_ms} | {error} |".format(
                case_id=case["case_id"],
                input_tokens=sum(candidate["input_tokens"] or 0 for candidate in candidates),
                output_tokens=sum(candidate["output_tokens"] or 0 for candidate in candidates),
                latency_ms=sum(candidate["latency_ms"] or 0 for candidate in candidates),
                error=(evidence.get("error") or {}).get("code", "—"),
            )
        )
    metric_table = "\n".join(metrics_rows)
    (root / "EVALUATION_REPORT.md").write_text(f"""# GENERALIZATION_BATCH_V1 Evaluation Report

本报告记录冻结管线的执行证据；外部 GPT 的盲评、合同审计和阶段归因尚待通过 Evaluation MCP 写入 `results/`。

## Case execution

| Case | Pipeline status | Run |
| --- | --- | --- |
{rows}

## External evaluation status

盲评胜负、Planner 合同 A/B 对比、Critic 命中/误报、Reviser 新增事实和 Judge 局部裁决均待独立 GPT 按 `GPT_EVALUATOR_PROMPT.md` 完成。CASE-002～004 在 Planner 基础设施失败后停止，因此没有文本可供盲评；它们不能被计入通过分母。

## Tokens, latency, and intervention

| Case | Input tokens | Output tokens | Total latency (ms) | Stage error |
| --- | ---: | ---: | ---: | --- |
{metric_table}

人工介入次数为 0；运行器没有重试、没有变更 Prompt，也没有改写候选或最终稿。

## Passing criteria

- 盲评最终稿胜出：至少 3/4。
- 关键 Planner 合同错误少于 Writer：至少 3/4。
- 最终稿没有新增重要 Planner 之外剧情：4/4。
- stop state 准确：至少 3/4。
- Judge 局部裁决没有明显退化：至少 3/4。

## Supported conclusions and limits

`pipeline_evidence.json` 保存每个 Candidate 的原始响应、解析输出、选择关系、token、延迟、错误和最终来源映射。当前证据只支持“CASE-001 已导出可盲评基准；CASE-002～004 的第一次 Planner 调用失败且已停止”。在外部评估完成且至少三个新增案例取得可比较正文前，不能支持“冻结管线比单次 Writer 更稳定”的结论。单个案例失败不会触发 Prompt 修改建议。
""", encoding="utf-8")


async def run(database: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            baseline = await _ensure_baseline(session, root)
            cases = [await _export_case_001(session, root)]
            for case_id, spec in CASE_SPECS.items():
                cases.append(await _run_case(session, root, case_id, spec, baseline))
            write_json(root / "cases_manifest.json", {"batch": "GENERALIZATION_BATCH_V1", "cases": cases})
            _write_prompt(root)
            _write_report(root, cases)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True, help="Frozen local SQLite database")
    parser.add_argument("--evaluation-root", type=Path, default=REPO_ROOT / "__evaluation")
    args = parser.parse_args()
    asyncio.run(run(args.database.resolve(), args.evaluation_root.resolve()))
