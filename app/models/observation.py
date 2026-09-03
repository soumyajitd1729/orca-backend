import uuid
from datetime import datetime
from typing import Optional

from geoalchemy2 import WKBElement
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import geometry
from app.models.enums import QualityFlag


class Observation(Base, TimestampMixin):
    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    variable: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    geometry: Mapped[Optional[WKBElement]] = mapped_column(
        geometry("POINT", 4326), nullable=True
    )
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("data_source_health.id", ondelete="SET NULL"), nullable=True
    )
    quality_flag: Mapped[QualityFlag] = mapped_column(
        SAEnum(QualityFlag, name="quality_flag"), nullable=False, default=QualityFlag.good
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    source: Mapped[Optional["DataSourceHealth"]] = relationship(back_populates="observations")
