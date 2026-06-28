from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False
    )

    username: Mapped[str | None]

    role: Mapped[str | None] = mapped_column(
        String,
        nullable=True
    )

    market_name: Mapped[str | None] = mapped_column(String, nullable=True)

    market_created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    business_photo_url: Mapped[str | None] = mapped_column(String, nullable=True)

    business_rating: Mapped[float] = mapped_column(Float, default=0.0)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    business_country: Mapped[str | None] = mapped_column(String, nullable=True)

    business_region: Mapped[str | None] = mapped_column(String, nullable=True)

    business_city: Mapped[str | None] = mapped_column(String, nullable=True)

    personal_country: Mapped[str | None] = mapped_column(String, nullable=True)

    personal_region: Mapped[str | None] = mapped_column(String, nullable=True)

    personal_city: Mapped[str | None] = mapped_column(String, nullable=True)

    linked_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    linked_chat_title: Mapped[str | None] = mapped_column(String, nullable=True)

    linked_chat_type: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )