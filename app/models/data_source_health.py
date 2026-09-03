import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import SourceStatus


class DataSourceHealth(Base, TimestampMixin):
    __tablename__ = "data_source_health"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[SourceStatus] = mapped_column(
        SAEnum(SourceStatus, name="source_status"),
        nullable=False,
        default=SourceStatus.unavailable,
    )
    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    observations: Mapped[list["Observation"]] = relationship(back_populates="source")
