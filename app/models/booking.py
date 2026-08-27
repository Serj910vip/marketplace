from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    client_name: Mapped[str] = mapped_column(String(100), nullable=False)

    client_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    client_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    booking_day: Mapped[str | None] = mapped_column(String(20), nullable=True)
    booking_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    """Устаревшие поля, сохранены для совместимости — используйте starts_at/ends_at."""

    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    """pending / confirmed / completed / cancelled_by_client / cancelled_by_owner / no_show"""

    price_at_booking: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
