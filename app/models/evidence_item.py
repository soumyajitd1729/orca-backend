import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EvidenceItem(Base, TimestampMixin):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    variable: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    url_ref: Mapped[str] = mapped_column(String(1024), nullable=True)
