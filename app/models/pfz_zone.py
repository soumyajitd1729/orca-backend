import uuid
from datetime import date, datetime
from typing import Optional

from geoalchemy2 import WKBElement
from sqlalchemy import Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import geometry, jsonb


class PFZZone(Base, TimestampMixin):
    __tablename__ = "pfz_zones"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    geometry: Mapped[Optional[WKBElement]] = mapped_column(
        geometry("POLYGON", 4326), nullable=True
    )
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    components: Mapped[dict] = mapped_column(jsonb(), nullable=False, default=dict)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    landing_center: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    depth: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    forecast_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
