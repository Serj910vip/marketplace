from datetime import time as time_

from sqlalchemy import ForeignKey, Integer, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)

    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    """0 = понедельник ... 6 = воскресенье"""

    time_start: Mapped[time_] = mapped_column(Time, nullable=False)

    time_end: Mapped[time_] = mapped_column(Time, nullable=False)

    slot_step_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Если не задан — берётся duration_minutes услуги"""
