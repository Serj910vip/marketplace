from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability_rule import AvailabilityRule
from app.models.booking import Booking
from app.models.service import Service

ACTIVE_BOOKING_STATUSES = ("pending", "confirmed")

MAX_SLOT_DAYS = 30
"""Не считаем слоты дальше этого горизонта, чтобы не генерировать бесконечность."""


class AvailabilityRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_rules(self, service_id: int) -> list[AvailabilityRule]:
        query = select(AvailabilityRule).where(AvailabilityRule.service_id == service_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def replace_rules(self, service_id: int, rules: list[dict]) -> list[AvailabilityRule]:
        """rules: [{"weekday": 0, "time_start": time(10,0), "time_end": time(18,0), "slot_step_minutes": None}, ...]"""
        existing = await self.get_rules(service_id)
        for rule in existing:
            await self.session.delete(rule)
        await self.session.flush()

        created = []
        for r in rules:
            rule = AvailabilityRule(
                service_id=service_id,
                weekday=r["weekday"],
                time_start=r["time_start"],
                time_end=r["time_end"],
                slot_step_minutes=r.get("slot_step_minutes"),
            )
            self.session.add(rule)
            created.append(rule)

        await self.session.commit()
        for rule in created:
            await self.session.refresh(rule)
        return created

    async def get_available_slots(
        self,
        service: Service,
        date_from: date,
        date_to: date,
    ) -> list[dict]:
        date_to = min(date_to, date_from + timedelta(days=MAX_SLOT_DAYS))

        rules = await self.get_rules(service.id)
        if not rules:
            return []

        duration_minutes = service.duration_minutes or service.training_duration or 30
        duration = timedelta(minutes=duration_minutes)

        query = select(Booking).where(
            Booking.service_id == service.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.starts_at.isnot(None),
            Booking.starts_at >= datetime.combine(date_from, time.min),
            Booking.starts_at < datetime.combine(date_to + timedelta(days=1), time.min),
        )
        result = await self.session.execute(query)
        bookings = list(result.scalars().all())

        occupied: dict[datetime, int] = {}
        for booking in bookings:
            occupied[booking.starts_at] = occupied.get(booking.starts_at, 0) + 1

        rules_by_weekday: dict[int, list[AvailabilityRule]] = {}
        for rule in rules:
            rules_by_weekday.setdefault(rule.weekday, []).append(rule)

        now = datetime.utcnow()
        slots: list[dict] = []
        day = date_from
        while day <= date_to:
            for rule in rules_by_weekday.get(day.weekday(), []):
                step = timedelta(minutes=rule.slot_step_minutes or duration_minutes)
                cursor = datetime.combine(day, rule.time_start)
                day_end = datetime.combine(day, rule.time_end)
                while cursor + duration <= day_end:
                    if cursor > now and occupied.get(cursor, 0) < service.capacity:
                        slots.append({"starts_at": cursor, "ends_at": cursor + duration})
                    cursor += step
            day += timedelta(days=1)

        slots.sort(key=lambda s: s["starts_at"])
        return slots

    async def is_slot_available(self, service: Service, starts_at: datetime, ends_at: datetime) -> bool:
        query = select(Booking).where(
            Booking.service_id == service.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.starts_at == starts_at,
        )
        result = await self.session.execute(query)
        occupied_count = len(list(result.scalars().all()))
        if occupied_count >= service.capacity:
            return False

        weekday = starts_at.weekday()
        rules = [r for r in await self.get_rules(service.id) if r.weekday == weekday]
        for rule in rules:
            rule_start = datetime.combine(starts_at.date(), rule.time_start)
            rule_end = datetime.combine(starts_at.date(), rule.time_end)
            if rule_start <= starts_at and ends_at <= rule_end:
                return True
        return False
