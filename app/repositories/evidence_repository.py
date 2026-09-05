import uuid
from datetime import datetime
from typing import Sequence

from app.db.session import AsyncSession
from app.models.evidence_item import EvidenceItem
from sqlalchemy import delete, select


async def get_evidence_by_task_id(
    db: AsyncSession, task_id: uuid.UUID
) -> Sequence[EvidenceItem]:
    stmt = select(EvidenceItem).where(EvidenceItem.task_id == task_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_evidence_by_source(
    db: AsyncSession, source: str
) -> Sequence[EvidenceItem]:
    stmt = select(EvidenceItem).where(EvidenceItem.source == source)
    result = await db.execute(stmt)
    return result.scalars().all()


async def add_evidence_item(db: AsyncSession, item: EvidenceItem) -> EvidenceItem:
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def batch_add_evidence_items(
    db: AsyncSession, items: Sequence[EvidenceItem]
) -> Sequence[EvidenceItem]:
    db.add_all(items)
    await db.commit()
    for item in items:
        await db.refresh(item)
    return items


async def delete_evidence_for_task(db: AsyncSession, task_id: uuid.UUID) -> None:
    stmt = delete(EvidenceItem).where(EvidenceItem.task_id == task_id)
    await db.execute(stmt)
    await db.commit()
