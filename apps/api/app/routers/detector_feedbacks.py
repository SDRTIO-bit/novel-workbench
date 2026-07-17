import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models.chapter import Chapter, ChapterVersion
from app.models.generation import GenerationCandidate, GenerationRun, GenerationStep
from app.models.project import Project
from app.repositories.detector_feedback_repository import DetectorFeedbackRepository
from app.schemas.detector_feedback import (
    DetectorFeedbackCreate,
    DetectorFeedbackUpdate,
    DetectorFeedbackSchema,
)
from app.errors import bad_request

router = APIRouter(prefix="/api/detector-feedbacks", tags=["detector_feedbacks"])


async def _require_reference(db: AsyncSession, statement, label: str) -> None:
    result = await db.execute(statement)
    if result.scalar_one_or_none() is None:
        raise bad_request("REFERENCE_MISMATCH", f"{label} 不存在或不属于此项目")


async def _validate_references(db: AsyncSession, project_id: str, data: DetectorFeedbackCreate | DetectorFeedbackUpdate):
    if not isinstance(data, DetectorFeedbackCreate):
        return

    await _require_reference(
        db,
        select(Project.id).where(Project.id == project_id),
        "project_id",
    )
    if data.chapter_id:
        await _require_reference(
            db,
            select(Chapter.id).where(
                Chapter.id == data.chapter_id,
                Chapter.project_id == project_id,
            ),
            "chapter_id",
        )
    if data.run_id:
        await _require_reference(
            db,
            select(GenerationRun.id).where(
                GenerationRun.id == data.run_id,
                GenerationRun.project_id == project_id,
            ),
            "run_id",
        )
    if data.candidate_id:
        await _require_reference(
            db,
            select(GenerationCandidate.id)
            .join(GenerationStep, GenerationCandidate.step_id == GenerationStep.id)
            .join(GenerationRun, GenerationStep.run_id == GenerationRun.id)
            .where(
                GenerationCandidate.id == data.candidate_id,
                GenerationRun.project_id == project_id,
            ),
            "candidate_id",
        )
    if data.chapter_version_id:
        await _require_reference(
            db,
            select(ChapterVersion.id)
            .join(Chapter, ChapterVersion.chapter_id == Chapter.id)
            .where(
                ChapterVersion.id == data.chapter_version_id,
                Chapter.project_id == project_id,
            ),
            "chapter_version_id",
        )


def _paragraph_count(text: str) -> int:
    numbered = [int(value) for value in re.findall(r"(?m)^\s*\[P(\d+)\]", text)]
    if numbered:
        return max(numbered)
    return len([paragraph for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()])


async def _reference_text(db: AsyncSession, *, candidate_id: str | None, chapter_version_id: str | None) -> str:
    if candidate_id:
        result = await db.execute(
            select(GenerationCandidate.text_output).where(GenerationCandidate.id == candidate_id)
        )
        return result.scalar_one_or_none() or ""
    if chapter_version_id:
        result = await db.execute(
            select(ChapterVersion.text).where(ChapterVersion.id == chapter_version_id)
        )
        return result.scalar_one_or_none() or ""
    return ""


async def _validate_span_bounds(
    db: AsyncSession,
    *,
    candidate_id: str | None,
    chapter_version_id: str | None,
    spans: list,
) -> None:
    if not spans:
        return
    paragraph_count = _paragraph_count(
        await _reference_text(
            db,
            candidate_id=candidate_id,
            chapter_version_id=chapter_version_id,
        )
    )
    if paragraph_count == 0:
        raise bad_request("SPAN_TARGET_EMPTY", "检测对象没有可标记的正文段落")
    for index, span in enumerate(spans):
        if span.end_paragraph > paragraph_count:
            raise bad_request(
                "SPAN_OUT_OF_RANGE",
                "人工区间超出检测对象的段落范围",
                {"span_index": index, "max_paragraph": paragraph_count},
            )


def _validate_ratio_total(human: float | None, suspected_ai: float | None, ai: float | None) -> None:
    if all(value is not None for value in (human, suspected_ai, ai)):
        total = human + suspected_ai + ai  # type: ignore[operator]
        if total < 99.5 or total > 100.5:
            raise bad_request(
                "INVALID_RATIO_TOTAL",
                "检测比例总和必须在 99.5-100.5 之间",
                {"total": total},
            )


@router.post("", response_model=DetectorFeedbackSchema, status_code=201)
async def create_feedback(
    data: DetectorFeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    await _validate_references(db, data.project_id, data)
    await _validate_span_bounds(
        db,
        candidate_id=data.candidate_id,
        chapter_version_id=data.chapter_version_id,
        spans=data.spans,
    )
    repo = DetectorFeedbackRepository(db)
    fb = await repo.create(data.model_dump())
    await db.commit()
    return fb


@router.get("", response_model=list[DetectorFeedbackSchema])
async def list_feedbacks(
    project_id: str = Query(...),
    chapter_id: str | None = Query(None),
    candidate_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = DetectorFeedbackRepository(db)
    return await repo.list_by_project(project_id, chapter_id, candidate_id)


@router.patch("/{feedback_id}", response_model=DetectorFeedbackSchema)
async def update_feedback(
    feedback_id: str,
    data: DetectorFeedbackUpdate,
    db: AsyncSession = Depends(get_db),
):
    repo = DetectorFeedbackRepository(db)
    fb = await repo.get_or_404(feedback_id)
    changes = data.model_dump(exclude_none=True)
    _validate_ratio_total(
        changes.get("human_ratio", fb.human_ratio),
        changes.get("suspected_ai_ratio", fb.suspected_ai_ratio),
        changes.get("ai_ratio", fb.ai_ratio),
    )
    if "spans" in changes:
        await _validate_span_bounds(
            db,
            candidate_id=fb.candidate_id,
            chapter_version_id=fb.chapter_version_id,
            spans=data.spans or [],
        )
    fb = await repo.update(fb, changes)
    await db.commit()
    return fb


@router.delete("/{feedback_id}")
async def delete_feedback(
    feedback_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo = DetectorFeedbackRepository(db)
    fb = await repo.get_or_404(feedback_id)
    await repo.delete(fb)
    await db.commit()
    return {"status": "ok"}
