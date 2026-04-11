from __future__ import annotations

from loguru import logger

from salon_gateway.models.booking import BookingDraft


class LoggingSink:
    """未接飞书时占位，仅记录结构化预约。"""

    async def append_booking(self, draft: BookingDraft) -> None:
        logger.info("booking_draft {}", draft.model_dump())
