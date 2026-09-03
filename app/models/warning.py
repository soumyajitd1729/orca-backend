import uuid
from datetime import datetime

from geoalchemy2 import WKBElement
from sqlalchemy import DateTime, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import geometry
from app.models.enums import WarningSeverity


class Warning(Base, TimestampMixin):
    __tablename__ = "warnings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[WarningSeverity] = mapped_column(
        SAEnum(WarningSeverity, name="warning_severity"), nullable=False
    )
    geometry: Mapped[WKBElement] = mapped_column(
        geometry("POLYGON", 4326), nullable=True
    )
    issued_by: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
