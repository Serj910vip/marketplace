import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(100), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    price: Mapped[float | None] = mapped_column(Float, nullable=True)

    training_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

    booking_format: Mapped[str | None] = mapped_column(String(20), nullable=True)

    working_schedule: Mapped[str | None] = mapped_column(Text, nullable=True)

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
