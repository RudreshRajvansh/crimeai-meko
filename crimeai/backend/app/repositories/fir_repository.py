"""Persistence for FIR reports, including the at-most-one-worker claim protocol."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fir import FIRReport

MAX_NLP_ATTEMPTS = 5
STALE_PROCESSING_AFTER = timedelta(minutes=15)


class FIRRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, fir_id: uuid.UUID) -> FIRReport | None:
        return await self.db.get(FIRReport, fir_id)

    async def get_by_fir_number(self, fir_number: str) -> FIRReport | None:
        result = await self.db.execute(select(FIRReport).where(FIRReport.fir_number == fir_number))
        return result.scalar_one_or_none()

    async def list_firs(
        self, nlp_status: str | None = None, submitted_by: uuid.UUID | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[FIRReport], int]:
        filters = []
        if nlp_status:
            filters.append(FIRReport.nlp_status == nlp_status)
        if submitted_by:
            filters.append(FIRReport.submitted_by == submitted_by)
        total = (await self.db.execute(select(func.count(FIRReport.id)).where(*filters))).scalar_one()
        rows = await self.db.execute(
            select(FIRReport).where(*filters).order_by(FIRReport.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total

    async def create(self, **kwargs: Any) -> FIRReport:
        fir = FIRReport(**kwargs)
        self.db.add(fir)
        await self.db.flush()
        await self.db.refresh(fir)
        return fir

    async def claim(self, fir_id: uuid.UUID) -> FIRReport | None:
        """
        Atomically move a FIR into 'processing'. Returns None if another worker
        already holds it or it is done. A claim older than STALE_PROCESSING_AFTER
        is treated as abandoned (crashed worker) and may be taken over.
        """
        stale_before = datetime.now(UTC) - STALE_PROCESSING_AFTER
        result = await self.db.execute(
            update(FIRReport)
            .where(
                FIRReport.id == fir_id,
                FIRReport.nlp_attempts < MAX_NLP_ATTEMPTS,
                or_(
                    FIRReport.nlp_status.in_(("pending", "failed")),
                    (FIRReport.nlp_status == "processing") & (FIRReport.processing_started_at < stale_before),
                ),
            )
            .values(
                nlp_status="processing",
                processing_started_at=func.now(),
                nlp_attempts=FIRReport.nlp_attempts + 1,
            )
            .returning(FIRReport.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        await self.db.commit()
        fir = await self.get_by_id(fir_id)
        if fir is not None:
            await self.db.refresh(fir)
        return fir

    async def complete(self, fir_id: uuid.UUID, entities: dict, confidence: float, redacted_text: str) -> None:
        await self.db.execute(
            update(FIRReport).where(FIRReport.id == fir_id).values(
                extracted_entities=entities,
                extraction_confidence=confidence,
                redacted_text=redacted_text,
                nlp_status="completed",
                nlp_error=None,
            )
        )

    async def fail(self, fir_id: uuid.UUID, error: str, status: str = "failed") -> None:
        await self.db.execute(
            update(FIRReport).where(FIRReport.id == fir_id).values(nlp_status=status, nlp_error=error[:2000])
        )

    async def reset_for_reprocess(self, fir_id: uuid.UUID) -> None:
        await self.db.execute(
            update(FIRReport).where(FIRReport.id == fir_id).values(
                nlp_status="pending", nlp_attempts=0, nlp_error=None,
                # Uploaded documents are read again from the stored original, so OCR improvements apply.
                raw_text=case((FIRReport.file_url.is_not(None), ""), else_=FIRReport.raw_text),
            )
        )

    async def claimable_ids(self, limit: int = 100) -> list[uuid.UUID]:
        stale_before = datetime.now(UTC) - STALE_PROCESSING_AFTER
        rows = await self.db.execute(
            select(FIRReport.id)
            .where(
                FIRReport.nlp_attempts < MAX_NLP_ATTEMPTS,
                or_(
                    FIRReport.nlp_status.in_(("pending", "failed")),
                    (FIRReport.nlp_status == "processing") & (FIRReport.processing_started_at < stale_before),
                ),
            )
            .order_by(FIRReport.created_at)
            .limit(limit)
        )
        return list(rows.scalars().all())
