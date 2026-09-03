import uuid
from datetime import datetime

from geoalchemy2 import WKBElement
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import geometry


class MpaBoundary(Base, TimestampMixin):
    __tablename__ = "mpa_boundaries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geometry: Mapped[WKBElement] = mapped_column(
        geometry("MULTIPOLYGON", 4326), nullable=False
    )
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
