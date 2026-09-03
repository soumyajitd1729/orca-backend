import uuid
from datetime import datetime
from typing import Optional

from geoalchemy2 import WKBElement
from sqlalchemy import DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import geometry, jsonb


class PFZZone(Base, TimestampMixin):
    __tablename__ = "pfz_zones"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    geometry: Mapped[Optional[WKBElement]] = mapped_column(
        geometry("POLYGON", 4326), nullable=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[dict] = mapped_column(jsonb(), nullable=False, default=dict)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
