import json
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.detector_feedback import DetectorFeedback


class DetectorFeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: dict) -> DetectorFeedback:
        spans_json = json.dumps(data.pop("spans", []), ensure_ascii=False)
        fb = DetectorFeedback(spans_json=spans_json, **data)
        self.session.add(fb)
        await self.session.flush()
        return fb

    async def get(self, feedback_id: str) -> DetectorFeedback | None:
        stmt = select(DetectorFeedback).where(DetectorFeedback.id == feedback_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, feedback_id: str) -> DetectorFeedback:
        fb = await self.get(feedback_id)
        if not fb:
            from app.errors import not_found
            raise not_found("FEEDBACK_NOT_FOUND", "检测反馈不存在")
        return fb

    async def list_by_project(
        self,
        project_id: str,
        chapter_id: str | None = None,
        candidate_id: str | None = None,
    ) -> list[DetectorFeedback]:
        stmt = select(DetectorFeedback).where(
            DetectorFeedback.project_id == project_id
        )
        if chapter_id:
            stmt = stmt.where(DetectorFeedback.chapter_id == chapter_id)
        if candidate_id:
            stmt = stmt.where(DetectorFeedback.candidate_id == candidate_id)
        stmt = stmt.order_by(DetectorFeedback.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, feedback: DetectorFeedback, data: dict) -> DetectorFeedback:
        if "spans" in data:
            data["spans_json"] = json.dumps(data.pop("spans"), ensure_ascii=False)
        for key, value in data.items():
            if hasattr(feedback, key) and value is not None:
                setattr(feedback, key, value)
        await self.session.flush()
        return feedback

    async def delete(self, feedback: DetectorFeedback) -> None:
        await self.session.delete(feedback)
        await self.session.flush()
