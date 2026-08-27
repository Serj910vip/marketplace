import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_categories.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(100), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """Устаревшее свободнотекстовое поле, сохранено для совместимости — используйте category_id."""

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    training_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Устаревшее имя, сохранено для совместимости — используйте duration_minutes."""

    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="published", nullable=False)
    """draft / published / hidden / archived"""

    booking_format: Mapped[str | None] = mapped_column(String(20), nullable=True)

    working_schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Устаревшее поле, заменено таблицей availability_rules."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    def get_schedule(self) -> dict:
        if not self.working_schedule:
            return {}
        try:
            return json.loads(self.working_schedule)
        except json.JSONDecodeError:
            return {}
