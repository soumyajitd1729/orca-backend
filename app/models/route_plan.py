import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import jsonb
from app.models.enums import RouteStatus


class RoutePlan(Base, TimestampMixin):
    __tablename__ = "route_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    waypoints: Mapped[dict] = mapped_column(jsonb(), nullable=False, default=dict)
    departure_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[RouteStatus] = mapped_column(
        SAEnum(RouteStatus, name="route_status"), nullable=False, default=RouteStatus.draft
    )

    user: Mapped[Optional["User"]] = relationship(back_populates="route_plans")
